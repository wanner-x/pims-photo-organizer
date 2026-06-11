from pathlib import Path
from collections.abc import Iterable, Iterator
from itertools import islice


DEFAULT_MEDIA_SUFFIXES = {
    ".arw",
    ".cr3",
    ".dng",
    ".gif",
    ".jpeg",
    ".jpg",
    ".mp4",
    ".nef",
    ".raf",
    ".wmv",
}


class ScanService:
    def iter_paths(
        self,
        root: Path,
        suffixes: Iterable[str] | None = None,
    ) -> Iterator[Path]:
        allowed_suffixes = {suffix.lower() for suffix in suffixes} if suffixes else None
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            if allowed_suffixes is not None and path.suffix.lower() not in allowed_suffixes:
                continue
            yield path

    def discover_paths(
        self,
        root: Path,
        limit: int | None = None,
        suffixes: Iterable[str] | None = None,
    ) -> list[Path]:
        paths = self.iter_paths(root, suffixes=suffixes)
        if limit is None:
            return sorted(paths)
        return sorted(islice(paths, limit))
