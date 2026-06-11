from collections import defaultdict
from pathlib import Path


def group_by_parent_folder(assets: list[dict]) -> list[dict]:
    grouped: dict[str, list[int]] = defaultdict(list)
    for asset in assets:
        parent = Path(asset["original_path"]).parent.as_posix()
        grouped[parent].append(asset["id"])
    return [
        {"source_root": source_root, "asset_ids": asset_ids}
        for source_root, asset_ids in sorted(grouped.items())
    ]
