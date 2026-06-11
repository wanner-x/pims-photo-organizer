from pathlib import Path


def stat_metadata(path: Path) -> dict[str, int | float | str]:
    stat = path.stat()
    return {
        "file_name": path.name,
        "file_size": stat.st_size,
        "mtime": stat.st_mtime,
        "suffix": path.suffix.lower(),
    }
