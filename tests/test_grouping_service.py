from pims_v1.services.grouping_service import group_by_parent_folder


def test_group_by_parent_folder_builds_candidate_sets():
    assets = [
        {"id": 1, "original_path": "/library/set1/a.jpg"},
        {"id": 2, "original_path": "/library/set1/b.jpg"},
        {"id": 3, "original_path": "/library/set2/c.jpg"},
    ]

    groups = group_by_parent_folder(assets)

    assert groups == [
        {"source_root": "/library/set1", "asset_ids": [1, 2]},
        {"source_root": "/library/set2", "asset_ids": [3]},
    ]
