from pathlib import Path
import shutil

from pims_v1.services.archive_service import copy_to_archive, verify_archive_copy


def move_to_quarantine(source: Path, quarantine_root: Path) -> Path:
    quarantine_root.mkdir(parents=True, exist_ok=True)
    destination = quarantine_root / source.name
    shutil.move(str(source), str(destination))
    return destination


def archive_and_quarantine_if_verified(
    source: Path,
    archive_target: Path,
    quarantine_root: Path,
) -> dict[str, Path]:
    archived = copy_to_archive(source, archive_target)
    if not verify_archive_copy(source, archived):
        raise ValueError("archive verification failed")
    quarantined = move_to_quarantine(source, quarantine_root)
    return {"archived": archived, "quarantined": quarantined}
