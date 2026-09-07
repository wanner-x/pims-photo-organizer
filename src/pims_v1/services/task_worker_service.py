from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path
import warnings

import imagehash
from PIL import Image
from sqlalchemy.orm import Session

from pims_v1.models.asset import Asset
from pims_v1.models.processing import ProcessingTask
from pims_v1.services.hash_service import md5_file_bytes
# Importing image_open_service applies the global Pillow limits (MAX_IMAGE_PIXELS,
# LOAD_TRUNCATED_IMAGES) relied on by the thread-safe compute helper below.
import pims_v1.services.image_open_service  # noqa: F401
from pims_v1.services.phash_index_service import IMAGE_SUFFIXES, PHASH_PRESCALE


def _compute_phash_for_path(path: str) -> tuple[str | None, str | None]:
    """Read an image and compute its perceptual hash. Pure compute with no DB or
    shared mutable state, so it is safe to run across threads. Returns
    ``(phash, None)`` on success or ``(None, error_message)`` on failure.

    Unlike ``safe_image_open`` this does not touch the global ``warnings`` filter
    state (which is not thread-safe); it relies on the process-wide Pillow limits
    already configured at import time.
    """
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(path) as image:
                try:
                    image.draft(None, PHASH_PRESCALE)
                except (OSError, ValueError):
                    pass
                return str(imagehash.phash(image)), None
    except Exception as exc:  # noqa: BLE001 - report any decode/IO failure to the caller
        return None, str(exc)


ProgressCallback = Callable[[dict[str, int | str]], None]


def _utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _pending_tasks(session: Session, task_type: str, limit: int) -> list[ProcessingTask]:
    return (
        session.query(ProcessingTask)
        .filter(ProcessingTask.status == "pending", ProcessingTask.task_type == task_type)
        .order_by(ProcessingTask.id)
        .limit(limit)
        .all()
    )


def _mark_running(task: ProcessingTask) -> None:
    task.status = "running"
    task.attempts += 1
    task.heartbeat_at = _utc_now()
    task.last_error = None


def _mark_completed(task: ProcessingTask) -> None:
    task.status = "completed"
    task.heartbeat_at = _utc_now()
    task.last_error = None


def _mark_failed(task: ProcessingTask, error: str) -> None:
    task.status = "failed"
    task.heartbeat_at = _utc_now()
    task.last_error = error[:2048]


def _emit_progress(
    *,
    task_type: str,
    summary: dict[str, int],
    seen: int,
    progress_callback: ProgressCallback | None,
) -> None:
    if progress_callback is None:
        return
    progress_callback({"task_type": task_type, "seen": seen, **summary})


def process_md5_tasks(
    *,
    session: Session,
    limit: int,
    max_bytes: int | None = None,
    commit_interval: int = 100,
    progress_interval: int = 100,
    progress_callback: ProgressCallback | None = None,
) -> dict[str, int]:
    summary = {"processed": 0, "failed": 0, "skipped_oversize": 0}
    seen = 0

    for task in _pending_tasks(session, "hash_md5", limit):
        seen += 1
        _mark_running(task)
        asset = session.get(Asset, task.subject_id)
        if asset is None:
            _mark_failed(task, f"missing asset: {task.subject_id}")
            summary["failed"] += 1
        elif max_bytes is not None and asset.file_size > max_bytes:
            asset.stage = "md5_skipped_oversize"
            _mark_completed(task)
            summary["skipped_oversize"] += 1
        else:
            path = Path(asset.current_path or asset.original_path)
            if not path.exists():
                asset.status = "missing"
                asset.stage = "md5_missing"
                _mark_failed(task, f"missing file: {path}")
                summary["failed"] += 1
            else:
                asset.hash_md5 = md5_file_bytes(path)
                asset.stage = "md5_done"
                _mark_completed(task)
                summary["processed"] += 1

        if seen % commit_interval == 0:
            session.commit()
        if seen % progress_interval == 0:
            _emit_progress(
                task_type="hash_md5",
                summary=summary,
                seen=seen,
                progress_callback=progress_callback,
            )

    session.commit()
    if seen and seen % progress_interval != 0:
        _emit_progress(
            task_type="hash_md5",
            summary=summary,
            seen=seen,
            progress_callback=progress_callback,
        )
    return summary


def process_phash_tasks(
    *,
    session: Session,
    limit: int,
    commit_interval: int = 50,
    progress_interval: int = 50,
    concurrency: int = 1,
    progress_callback: ProgressCallback | None = None,
) -> dict[str, int]:
    summary = {"processed": 0, "failed": 0, "skipped_non_image": 0}

    tasks = _pending_tasks(session, "hash_phash", limit)
    # Resolve each task synchronously (all DB access stays on this thread) and
    # collect the image-decode jobs that need the slow NAS read + hash.
    pending_compute: list[tuple[ProcessingTask, Asset, str]] = []
    seen = 0
    for task in tasks:
        seen += 1
        _mark_running(task)
        asset = session.get(Asset, task.subject_id)
        if asset is None:
            _mark_failed(task, f"missing asset: {task.subject_id}")
            summary["failed"] += 1
        elif asset.file_ext.lower() not in IMAGE_SUFFIXES:
            asset.stage = "phash_skipped_non_image"
            _mark_completed(task)
            summary["skipped_non_image"] += 1
        else:
            path = Path(asset.current_path or asset.original_path)
            if not path.exists():
                asset.status = "missing"
                asset.stage = "phash_missing"
                _mark_failed(task, f"missing file: {path}")
                summary["failed"] += 1
            else:
                pending_compute.append((task, asset, str(path)))

    def _apply_result(task: ProcessingTask, asset: Asset, phash: str | None, error: str | None) -> None:
        if error is not None:
            asset.status = "invalid_image"
            asset.stage = "phash_failed"
            _mark_failed(task, f"phash failed: {error}")
            summary["failed"] += 1
        else:
            asset.hash_phash = phash
            asset.stage = "phash_done"
            _mark_completed(task)
            summary["processed"] += 1

    done = 0

    def _checkpoint() -> None:
        if done % commit_interval == 0:
            session.commit()
        if done % progress_interval == 0:
            _emit_progress(
                task_type="hash_phash",
                summary=summary,
                seen=done,
                progress_callback=progress_callback,
            )

    if concurrency > 1 and len(pending_compute) > 1:
        # Decode + hash in parallel (NAS-I/O bound), but apply every result back
        # to the DB here on the single owning thread.
        with ThreadPoolExecutor(max_workers=concurrency) as executor:
            futures = {
                executor.submit(_compute_phash_for_path, path): (task, asset)
                for task, asset, path in pending_compute
            }
            for future in as_completed(futures):
                task, asset = futures[future]
                phash, error = future.result()
                _apply_result(task, asset, phash, error)
                done += 1
                _checkpoint()
    else:
        for task, asset, path in pending_compute:
            phash, error = _compute_phash_for_path(path)
            _apply_result(task, asset, phash, error)
            done += 1
            _checkpoint()

    session.commit()
    if done % progress_interval != 0:
        _emit_progress(
            task_type="hash_phash",
            summary=summary,
            seen=done,
            progress_callback=progress_callback,
        )
    return summary
