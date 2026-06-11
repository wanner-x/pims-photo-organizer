from pathlib import Path

from PIL import Image, UnidentifiedImageError
from sqlalchemy.orm import Session

from pims_v1.models.asset import Asset
from pims_v1.services.phash_index_service import IMAGE_SUFFIXES


def ensure_thumbnail(
    *,
    session: Session,
    asset_id: int,
    cache_root: str | Path,
    size: tuple[int, int] = (320, 320),
) -> dict[str, int | str | None]:
    asset = session.get(Asset, asset_id)
    if asset is None:
        raise ValueError(f"Asset not found: {asset_id}")

    if asset.file_ext.lower() not in IMAGE_SUFFIXES:
        return {"asset_id": asset.id, "status": "skipped_non_image", "path": None}

    source = Path(asset.current_path or asset.original_path)
    if not source.exists():
        return {"asset_id": asset.id, "status": "missing", "path": None}

    thumbnail_dir = Path(cache_root) / "thumbnails"
    thumbnail_dir.mkdir(parents=True, exist_ok=True)
    destination = thumbnail_dir / f"{asset.id}.jpg"
    if destination.exists():
        return {"asset_id": asset.id, "status": "exists", "path": str(destination)}

    try:
        with Image.open(source) as image:
            image.thumbnail(size)
            image.convert("RGB").save(destination, "JPEG", quality=85)
    except (OSError, UnidentifiedImageError):
        return {"asset_id": asset.id, "status": "failed", "path": None}

    return {"asset_id": asset.id, "status": "created", "path": str(destination)}
