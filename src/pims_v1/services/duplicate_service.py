from collections import defaultdict


def group_exact_duplicates(assets: list[dict]) -> list[dict]:
    grouped: dict[str, list[int]] = defaultdict(list)
    for asset in assets:
        if asset["hash_md5"]:
            grouped[asset["hash_md5"]].append(asset["id"])
    return [
        {"hash_md5": digest, "asset_ids": asset_ids}
        for digest, asset_ids in grouped.items()
        if len(asset_ids) > 1
    ]
