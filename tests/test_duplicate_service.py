from pims_v1.services.duplicate_service import group_exact_duplicates


def test_group_exact_duplicates_by_md5():
    assets = [
        {"id": 1, "hash_md5": "aaa", "path": "A"},
        {"id": 2, "hash_md5": "aaa", "path": "B"},
        {"id": 3, "hash_md5": "bbb", "path": "C"},
    ]

    groups = group_exact_duplicates(assets)

    assert groups == [{"hash_md5": "aaa", "asset_ids": [1, 2]}]
