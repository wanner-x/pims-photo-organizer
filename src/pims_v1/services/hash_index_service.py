from pathlib import Path

from sqlalchemy.orm import Session

from pims_v1.repos.asset_repo import list_assets_missing_md5
from pims_v1.services.hash_service import md5_file_bytes


def compute_missing_md5(
    *,
    session: Session,
    limit: int | None = None,
    max_bytes: int | None = None,
) -> dict[str, int]:
    summary = {"processed": 0, "skipped_missing": 0, "skipped_oversize": 0}
    assets = list_assets_missing_md5(session, limit=limit)

    for asset in assets:
        path = Path(asset.current_path or asset.original_path)
        if not path.exists():
            summary["skipped_missing"] += 1
            continue
        if max_bytes is not None and asset.file_size > max_bytes:
            summary["skipped_oversize"] += 1
            continue

        asset.hash_md5 = md5_file_bytes(path)
        asset.stage = "md5_done"
        summary["processed"] += 1

    session.commit()
    return summary
