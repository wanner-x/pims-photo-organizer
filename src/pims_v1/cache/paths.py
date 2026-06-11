from pathlib import Path


def shard_cache_path(cache_root: Path, digest: str, suffix: str) -> Path:
    return cache_root / digest[:2] / digest[2:4] / f"{digest}{suffix}"
