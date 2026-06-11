from pathlib import Path

from sqlalchemy.orm import Session

from pims_v1.repos.asset_repo import upsert_discovered_asset
from pims_v1.repos.library_repo import get_or_create_library
from pims_v1.services.metadata_service import stat_metadata
from pims_v1.services.scan_service import DEFAULT_MEDIA_SUFFIXES, ScanService


def index_library(
    *,
    session: Session,
    name: str,
    kind: str,
    root_path: Path,
    limit: int | None,
) -> dict[str, int]:
    library = get_or_create_library(
        session=session,
        name=name,
        kind=kind,
        root_path=str(root_path),
    )
    service = ScanService()
    paths = service.discover_paths(root_path, limit=limit, suffixes=DEFAULT_MEDIA_SUFFIXES)
    summary = {"discovered": len(paths), "created": 0, "updated": 0}

    for path in paths:
        metadata = stat_metadata(path)
        _, created = upsert_discovered_asset(
            session=session,
            library_id=library.id,
            original_path=str(path),
            file_name=str(metadata["file_name"]),
            file_ext=str(metadata["suffix"]),
            file_size=int(metadata["file_size"]),
            mtime=float(metadata["mtime"]),
        )
        if created:
            summary["created"] += 1
        else:
            summary["updated"] += 1

    session.commit()
    return summary
