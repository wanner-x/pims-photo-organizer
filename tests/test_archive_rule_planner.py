from pims_v1.services.archive_rule_planner import plan_archive_from_source_root


def test_plan_archive_for_named_person_series_preserves_parent_and_metadata():
    plan = plan_archive_from_source_root(
        "D:/图册/雪琪SAMA/雪琪SAMA 透明女仆 [43P4V234MB]"
    )

    assert plan["category"] == "雪琪SAMA"
    assert plan["title"] == "雪琪SAMA 透明女仆 [43P4V234MB]"
    assert plan["confidence"] >= 0.9
    assert "parent_directory_match" in plan["matched_rules"]


def test_plan_archive_for_project_series_preserves_project_root():
    plan = plan_archive_from_source_root(
        "D:/图册/紧急企划/【紧急企划】-【VOL.001】-【樱樱樱可】-【JK黑】-【45P1V-858M】"
    )

    assert plan["category"] == "紧急企划"
    assert plan["title"] == "【紧急企划】-【VOL.001】-【樱樱樱可】-【JK黑】-【45P1V-858M】"
    assert plan["metadata"]["has_volume"] is True


def test_plan_archive_for_imiss_series_uses_brand_bucket_when_parent_is_generic():
    plan = plan_archive_from_source_root(
        "D:/图册/[IMISS爱蜜社] 2025.08.27 VOL.800 许诺Sabrina [86+1P]"
    )

    assert plan["category"] == "IMISS爱蜜社"
    assert plan["title"] == "[IMISS爱蜜社] 2025.08.27 VOL.800 许诺Sabrina [86+1P]"
    assert plan["metadata"]["has_metadata_suffix"] is True
