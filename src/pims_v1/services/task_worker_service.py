from pathlib import Path

import imagehash
from PIL import Image, UnidentifiedImageError
from sqlalchemy.orm import Session

from pims_v1.models.asset import Asset
from pims_v1.services.hash_service import md5_file_bytes
from pims_v1.services.phash_index_service import IMAGE_SUFFIXES
from pims_v1.services.task_service import claim_next_task, complete_task, fail_task


def process_md5_tasks(
    *,
    session: Session,
    limit: int,
    max_bytes: int | None = None,
) -> dict[str, int]:
    summary = {"processed": 0, "failed": 0, "skipped_oversize": 0}

    for _ in range(limit):
        task = claim_next_task(session, task_type="hash_md5")
        if task is None:
            break

        asset = session.get(Asset, task.subject_id)
        if asset is None:
            fail_task(session, task.id, f"missing asset: {task.subject_id}")
            summary["failed"] += 1
            continue

        path = Path(asset.current_path or asset.original_path)
        if not path.exists():
            fail_task(session, task.id, f"missing file: {path}")
            summary["failed"] += 1
            continue

        if max_bytes is not None and asset.file_size > max_bytes:
            asset.stage = "md5_skipped_oversize"
            complete_task(session, task.id)
            summary["skipped_oversize"] += 1
            continue

        asset.hash_md5 = md5_file_bytes(path)
        asset.stage = "md5_done"
        complete_task(session, task.id)
        summary["processed"] += 1

    session.commit()
    return summary


def process_phash_tasks(
    *,
    session: Session,
    limit: int,
) -> dict[str, int]:
    summary = {"processed": 0, "failed": 0, "skipped_non_image": 0}

    for _ in range(limit):
        task = claim_next_task(session, task_type="hash_phash")
        if task is None:
            break

        asset = session.get(Asset, task.subject_id)
        if asset is None:
            fail_task(session, task.id, f"missing asset: {task.subject_id}")
            summary["failed"] += 1
            continue

        if asset.file_ext.lower() not in IMAGE_SUFFIXES:
            asset.stage = "phash_skipped_non_image"
            complete_task(session, task.id)
            summary["skipped_non_image"] += 1
            continue

        path = Path(asset.current_path or asset.original_path)
        if not path.exists():
            fail_task(session, task.id, f"missing file: {path}")
            summary["failed"] += 1
            continue

        try:
            with Image.open(path) as image:
                asset.hash_phash = str(imagehash.phash(image))
        except (OSError, UnidentifiedImageError) as exc:
            fail_task(session, task.id, f"phash failed: {exc}")
            summary["failed"] += 1
            continue

        asset.stage = "phash_done"
        complete_task(session, task.id)
        summary["processed"] += 1

    session.commit()
    return summary
