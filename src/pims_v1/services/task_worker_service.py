from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import imagehash
from PIL import Image, UnidentifiedImageError
from sqlalchemy.orm import Session

from pims_v1.models.asset import Asset
from pims_v1.models.processing import ProcessingTask
from pims_v1.services.hash_service import md5_file_bytes
from pims_v1.services.phash_index_service import IMAGE_SUFFIXES


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
    progress_callback: ProgressCallback | None = None,
) -> dict[str, int]:
    summary = {"processed": 0, "failed": 0, "skipped_non_image": 0}
    seen = 0

    for task in _pending_tasks(session, "hash_phash", limit):
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
                _mark_failed(task, f"missing file: {path}")
                summary["failed"] += 1
            else:
                try:
                    with Image.open(path) as image:
                        asset.hash_phash = str(imagehash.phash(image))
                except (OSError, UnidentifiedImageError) as exc:
                    _mark_failed(task, f"phash failed: {exc}")
                    summary["failed"] += 1
                else:
                    asset.stage = "phash_done"
                    _mark_completed(task)
                    summary["processed"] += 1

        if seen % commit_interval == 0:
            session.commit()
        if seen % progress_interval == 0:
            _emit_progress(
                task_type="hash_phash",
                summary=summary,
                seen=seen,
                progress_callback=progress_callback,
            )

    session.commit()
    if seen and seen % progress_interval != 0:
        _emit_progress(
            task_type="hash_phash",
            summary=summary,
            seen=seen,
            progress_callback=progress_callback,
        )
    return summary
