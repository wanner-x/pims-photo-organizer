from pathlib import Path


class ScanService:
    def discover_paths(self, root: Path) -> list[Path]:
        return sorted(path for path in root.rglob("*") if path.is_file())
