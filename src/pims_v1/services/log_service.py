from pathlib import Path


def _read_log_text(path: Path) -> str:
    data = path.read_bytes()
    if data.startswith(b"\xff\xfe") or data.startswith(b"\xfe\xff"):
        return data.decode("utf-16", errors="replace")
    if b"\x00" in data[:200]:
        return data.decode("utf-16-le", errors="replace")
    return data.decode("utf-8", errors="replace")


def latest_log_tail(logs_root: str | Path, pattern: str = "full-detection-*.log", lines: int = 80) -> dict:
    root = Path(logs_root)
    if not root.exists():
        return {"found": False, "name": None, "lines": []}

    logs = sorted(
        root.glob(pattern),
        key=lambda path: (path.stat().st_mtime, path.name),
        reverse=True,
    )
    if not logs:
        return {"found": False, "name": None, "lines": []}

    latest = logs[0]
    safe_line_count = max(1, min(lines, 500))
    content = _read_log_text(latest).splitlines()
    return {
        "found": True,
        "name": latest.name,
        "lines": content[-safe_line_count:],
    }
