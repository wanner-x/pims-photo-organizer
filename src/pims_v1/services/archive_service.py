from pathlib import Path
import shutil


def copy_to_archive(source: Path, destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    return destination


def verify_archive_copy(source: Path, destination: Path) -> bool:
    return destination.exists() and source.stat().st_size == destination.stat().st_size
