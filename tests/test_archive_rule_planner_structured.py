from pims_v1.services.archive_rule_planner import plan_archive_from_source_root


def test_plan_archive_exposes_reviewable_structured_fields():
    plan = plan_archive_from_source_root(
        "D:/photos/[IMISS] 2025.08.27 VOL.800 Sabrina [86+1P]"
    )

    assert plan["archive_category"] == "IMISS"
    assert plan["archive_title"] == "[IMISS] 2025.08.27 VOL.800 Sabrina [86+1P]"
    assert plan["metadata"]["series_brand"] == "IMISS"
    assert plan["metadata"]["metadata_tokens"] == ["VOL.800", "86+1P"]
    assert plan["metadata"]["has_volume"] is True


def test_plan_uses_dirname_parser_for_person_folder_under_generic_parent():
    plan = plan_archive_from_source_root("D:/图册/雪琪SAMA JK白丝 [46P208MB]")

    assert plan["archive_category"] == "雪琪SAMA"
    assert plan["archive_title"] == "雪琪SAMA JK白丝 [46P208MB]"
    assert plan["metadata"]["category_type"] == "person"
    assert plan["metadata"]["parsed"]["persons"] == ["雪琪SAMA"]
    assert "dirname_parser_match" in plan["matched_rules"]
    assert plan["confidence"] >= 0.5


def test_plan_keeps_legacy_fallback_when_parser_confidence_is_low():
    plan = plan_archive_from_source_root("D:/图册/misc downloads backup")

    assert plan["archive_category"] == "misc downloads backup"
    assert plan["archive_title"] == "misc downloads backup"
    assert "fallback_folder_name" in plan["matched_rules"]
    assert plan["confidence"] == 0.82
    assert plan["metadata"]["category_type"] == "unknown"
    assert plan["metadata"]["parsed_confidence"] < 0.5


def test_plan_parent_match_still_wins_and_carries_parsed_metadata():
    plan = plan_archive_from_source_root(
        "D:/图册/雪琪SAMA/雪琪SAMA 透明女仆 [43P4V234MB]"
    )

    assert plan["archive_category"] == "雪琪SAMA"
    assert plan["confidence"] == 0.95
    assert "parent_directory_match" in plan["matched_rules"]
    parsed = plan["metadata"]["parsed"]
    assert parsed["specs"]["pictures"] == 43
    assert parsed["specs"]["videos"] == 4
    assert parsed["specs"]["size_mb"] == 234.0


def test_plan_uses_parser_for_project_folder_under_generic_parent():
    plan = plan_archive_from_source_root(
        "E:/图册整理/【紧急企划】-【VOL.001】-【樱樱樱可】-【JK黑】-【45P1V-858M】"
    )

    assert plan["archive_category"] == "紧急企划"
    assert plan["metadata"]["category_type"] == "project"
    assert plan["metadata"]["parsed"]["persons"] == ["樱樱樱可"]
    assert plan["metadata"]["parsed"]["numbers"][0]["raw"] == "VOL.001"
