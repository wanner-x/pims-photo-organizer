from pathlib import Path
import shutil
from urllib.parse import unquote, urlparse


def _sqlite_path_from_url(database_url: str) -> Path:
    parsed = urlparse(database_url)
    if parsed.scheme != "sqlite":
        raise ValueError("Only sqlite database backups are supported")
    if parsed.path in ("", "/"):
        raise ValueError("In-memory sqlite databases cannot be backed up")
    if parsed.netloc:
        return Path(f"//{parsed.netloc}{unquote(parsed.path)}")
    return Path(unquote(parsed.path.lstrip("/")))


def backup_sqlite_database(
    *,
    database_url: str,
    backup_dir: str | Path,
    label: str,
) -> dict[str, str]:
    source = _sqlite_path_from_url(database_url)
    if not source.exists():
        raise ValueError(f"Database file not found: {source}")

    backup_path = Path(backup_dir)
    backup_path.mkdir(parents=True, exist_ok=True)
    safe_label = "".join(char if char.isalnum() or char in ("-", "_") else "-" for char in label)
    destination = backup_path / f"{safe_label}-{source.name}"
    shutil.copy2(source, destination)
    return {"status": "created", "path": str(destination)}
