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
