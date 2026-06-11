from pathlib import Path

import imagehash
from PIL import Image, UnidentifiedImageError
from sqlalchemy.orm import Session

from pims_v1.models.asset import Asset

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".tif", ".tiff"}


def compute_missing_phash(*, session: Session, limit: int | None = None) -> dict[str, int]:
    summary = {"processed": 0, "skipped_missing": 0, "skipped_non_image": 0, "failed": 0}
    query = session.query(Asset).filter(Asset.hash_phash.is_(None)).order_by(Asset.id)
    if limit is not None:
        query = query.limit(limit)

    for asset in query.all():
        if asset.file_ext.lower() not in IMAGE_SUFFIXES:
            summary["skipped_non_image"] += 1
            continue
        path = Path(asset.current_path or asset.original_path)
        if not path.exists():
            summary["skipped_missing"] += 1
            continue
        try:
            with Image.open(path) as image:
                asset.hash_phash = str(imagehash.phash(image))
        except (OSError, UnidentifiedImageError):
            summary["failed"] += 1
            continue

        asset.stage = "phash_done"
        summary["processed"] += 1

    session.commit()
    return summary
