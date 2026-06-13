from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from pims_v1.db import Base
from pims_v1.models import archive_decision, asset, duplicate, library, operation, processing, review, series
from pims_v1.models.archive_decision import ArchiveExecutionRecord, ArchivePlanningRecord, ArchiveRiskEvent
from pims_v1.models.asset import Asset
from pims_v1.models.duplicate import DuplicateGroup, DuplicateGroupAsset
from pims_v1.models.library import Library
from pims_v1.models.series_moderation import SeriesModerationRun
from pims_v1.models.similar import SimilarGroup, SimilarGroupAsset
from pims_v1.models.series import SeriesCandidate, SeriesCandidateAsset, SeriesSuggestion
from pims_v1.services.review_service import (
    get_archive_review_overview,
    list_archive_anomalies,
    list_archive_execution_ledger,
    list_archive_sampling_queue,
    list_exact_duplicate_groups,
    list_series_review_candidates,
    list_series_candidates,
    list_similar_groups,
)


def make_session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}", future=True)
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    return session_factory()


def test_list_series_candidates_returns_counts(tmp_path):
    session = make_session(tmp_path)
    library_row = Library(name="Library", kind="local", root_path="/library")
    session.add(library_row)
    session.flush()
    first = Asset(
        library_id=library_row.id,
        original_path="/library/set1/a.jpg",
        current_path="/library/set1/a.jpg",
        file_name="a.jpg",
        file_ext=".jpg",
        file_size=1,
        mtime=1.0,
    )
    second = Asset(
        library_id=library_row.id,
        original_path="/library/set1/b.jpg",
        current_path="/library/set1/b.jpg",
        file_name="b.jpg",
        file_ext=".jpg",
        file_size=1,
        mtime=1.0,
    )
    session.add_all([first, second])
    session.flush()
    candidate = SeriesCandidate(library_id=library_row.id, source_root="/library/set1", title="set1")
    session.add(candidate)
    session.flush()
    session.add_all(
        [
            SeriesCandidateAsset(candidate_id=candidate.id, asset_id=first.id, sort_order=0),
            SeriesCandidateAsset(candidate_id=candidate.id, asset_id=second.id, sort_order=1),
        ]
    )
    session.commit()

    candidates = list_series_candidates(session, limit=10)

    assert candidates == [
        {
            "id": candidate.id,
            "title": "set1",
            "source_root": "/library/set1",
            "asset_count": 2,
            "status": "pending",
        }
    ]


def test_list_series_review_candidates_includes_suggestion_and_sample_assets(tmp_path):
    session = make_session(tmp_path)
    library_row = Library(name="Library", kind="local", root_path="/library")
    session.add(library_row)
    session.flush()
    asset_row = Asset(
        library_id=library_row.id,
        original_path="/library/set1/a.jpg",
        current_path="/library/set1/a.jpg",
        file_name="a.jpg",
        file_ext=".jpg",
        file_size=1,
        mtime=1.0,
    )
    session.add(asset_row)
    session.flush()
    candidate = SeriesCandidate(
        library_id=library_row.id,
        source_root="/library/set1",
        title="set1",
        status="ai_suggested",
    )
    session.add(candidate)
    session.flush()
    session.add(SeriesCandidateAsset(candidate_id=candidate.id, asset_id=asset_row.id, sort_order=0))
    suggestion = SeriesSuggestion(
        candidate_id=candidate.id,
        suggested_title="清晨写真",
        suggested_category="写真合集",
        suggested_archive_path="/nas/写真合集/清晨写真",
        plan_summary="移动到 NAS 目标目录",
        risk_flags='["目标目录已存在"]',
        content_tags='["R18","JK黑"]',
        r18_label=True,
        r18_confidence=0.9,
        r18_reason="目录名已有 R18",
        confidence=0.8,
        status="pending_review",
    )
    session.add(suggestion)
    session.commit()

    candidates = list_series_review_candidates(session, limit=10)

    assert candidates == [
        {
            "id": candidate.id,
            "title": "set1",
            "source_root": "/library/set1",
            "asset_count": 1,
            "status": "ai_suggested",
            "suggestion": {
                "id": suggestion.id,
                "title": "清晨写真",
                "category": "写真合集",
                "archive_path": "/nas/写真合集/清晨写真",
                "plan_summary": "移动到 NAS 目标目录",
                "risk_flags": ["目标目录已存在"],
                "tags": ["R18", "JK黑"],
                "r18_label": True,
                "r18_confidence": 0.9,
                "r18_reason": "目录名已有 R18",
                "confidence": 0.8,
                "status": "pending_review",
            },
            "assets": [
                {
                    "id": asset_row.id,
                    "file_name": "a.jpg",
                    "current_path": "/library/set1/a.jpg",
                    "file_ext": ".jpg",
                    "file_size": 1,
                    "thumbnail_url": f"/thumbnails/{asset_row.id}.jpg",
                    "media_url": f"/media/assets/{asset_row.id}",
                }
            ],
        }
    ]


def test_list_series_review_candidates_hides_confirmed_by_default(tmp_path):
    session = make_session(tmp_path)
    library_row = Library(name="Library", kind="local", root_path="/library")
    session.add(library_row)
    session.flush()
    candidate = SeriesCandidate(
        library_id=library_row.id,
        source_root="/library/set1",
        title="set1",
        status="confirmed",
    )
    session.add(candidate)
    session.flush()
    session.add(
        SeriesSuggestion(
            candidate_id=candidate.id,
            suggested_title="清晨写真",
            suggested_category="写真合集",
            confidence=0.8,
            status="confirmed",
        )
    )
    session.commit()

    candidates = list_series_review_candidates(session, limit=10)

    assert candidates == []


def test_list_series_review_candidates_includes_latest_moderation_summary(tmp_path):
    session = make_session(tmp_path)
    library_row = Library(name="Library", kind="local", root_path="/library")
    session.add(library_row)
    session.flush()
    asset_row = Asset(
        library_id=library_row.id,
        original_path="/library/set1/a.jpg",
        current_path="/library/set1/a.jpg",
        file_name="a.jpg",
        file_ext=".jpg",
        file_size=1,
        mtime=1.0,
    )
    session.add(asset_row)
    session.flush()
    candidate = SeriesCandidate(
        library_id=library_row.id,
        source_root="/library/set1",
        title="set1",
        status="pending_review",
    )
    session.add(candidate)
    session.flush()
    session.add(SeriesCandidateAsset(candidate_id=candidate.id, asset_id=asset_row.id, sort_order=0))
    session.add(
        SeriesModerationRun(
            candidate_id=candidate.id,
            provider="heuristic",
            mode="manual",
            status="completed",
            total_samples=3,
            flagged_samples=1,
            max_score=0.91,
            summary_json='{"r18_label": true, "r18_confidence": 0.91, "r18_reason": "visual provider heuristic flagged 1 samples", "risk_flags": ["visual_r18_suspected"], "sample_count": 3, "positive_samples": 1}',
        )
    )
    session.commit()

    candidates = list_series_review_candidates(session, limit=10)

    assert candidates[0]["moderation"]["r18_label"] is True
    assert candidates[0]["moderation"]["provider"] == "heuristic"
    assert candidates[0]["moderation"]["sample_count"] == 3


def test_list_series_review_candidates_filters_operational_queues(tmp_path):
    session = make_session(tmp_path)
    library_row = Library(name="Library", kind="local", root_path="/library")
    session.add(library_row)
    session.flush()

    def add_candidate(name: str, *, suggestion_payload: dict | None = None, moderation_payload: str | None = None):
        asset_row = Asset(
            library_id=library_row.id,
            original_path=f"/library/{name}/a.jpg",
            current_path=f"/library/{name}/a.jpg",
            file_name="a.jpg",
            file_ext=".jpg",
            file_size=1,
            mtime=1.0,
        )
        session.add(asset_row)
        session.flush()
        candidate = SeriesCandidate(library_id=library_row.id, source_root=f"/library/{name}", title=name, status="pending")
        session.add(candidate)
        session.flush()
        session.add(SeriesCandidateAsset(candidate_id=candidate.id, asset_id=asset_row.id, sort_order=0))
        if suggestion_payload is not None:
            session.add(
                SeriesSuggestion(
                    candidate_id=candidate.id,
                    suggested_title=suggestion_payload.get("title", name),
                    suggested_category=suggestion_payload.get("category", "People"),
                    confidence=suggestion_payload.get("confidence", 0.9),
                    risk_flags=suggestion_payload.get("risk_flags", "[]"),
                    content_tags=suggestion_payload.get("content_tags", "[]"),
                    r18_label=suggestion_payload.get("r18_label", False),
                    status=suggestion_payload.get("status", "pending_review"),
                )
            )
            candidate.status = "ai_suggested"
        if moderation_payload is not None:
            session.add(
                SeriesModerationRun(
                    candidate_id=candidate.id,
                    provider="heuristic",
                    mode="workflow",
                    status="completed",
                    total_samples=1,
                    flagged_samples=1,
                    max_score=0.91,
                    summary_json=moderation_payload,
                )
            )
        return candidate

    needs_ai = add_candidate("needs-ai")
    pending_confirm = add_candidate("pending-confirm", suggestion_payload={"confidence": 0.9})
    low_confidence = add_candidate("low-confidence", suggestion_payload={"confidence": 0.4})
    target_conflict = add_candidate(
        "target-conflict",
        suggestion_payload={"risk_flags": '["target_conflict"]'},
    )
    r18 = add_candidate(
        "r18",
        suggestion_payload={"r18_label": True, "content_tags": '["R18"]'},
        moderation_payload='{"r18_label": true, "risk_flags": ["visual_r18_suspected"], "sample_count": 1}',
    )
    session.commit()

    assert [item["id"] for item in list_series_review_candidates(session, review_filter="needs_ai")] == [needs_ai.id]
    assert [item["id"] for item in list_series_review_candidates(session, review_filter="pending_confirm")] == [
        pending_confirm.id,
        low_confidence.id,
        target_conflict.id,
        r18.id,
    ]
    assert [item["id"] for item in list_series_review_candidates(session, review_filter="low_confidence")] == [
        low_confidence.id
    ]
    assert [item["id"] for item in list_series_review_candidates(session, review_filter="target_conflict")] == [
        target_conflict.id
    ]
    assert [item["id"] for item in list_series_review_candidates(session, review_filter="r18")] == [r18.id]


def test_list_exact_duplicate_groups_returns_member_assets(tmp_path):
    session = make_session(tmp_path)
    library_row = Library(name="Library", kind="local", root_path="/library")
    session.add(library_row)
    session.flush()
    first = Asset(
        library_id=library_row.id,
        original_path="/library/a.jpg",
        current_path="/library/a.jpg",
        file_name="a.jpg",
        file_ext=".jpg",
        file_size=10,
        mtime=1.0,
        hash_md5="same",
    )
    second = Asset(
        library_id=library_row.id,
        original_path="/library/b.jpg",
        current_path="/library/b.jpg",
        file_name="b.jpg",
        file_ext=".jpg",
        file_size=20,
        mtime=2.0,
        hash_md5="same",
    )
    session.add_all([first, second])
    session.flush()
    group = DuplicateGroup(hash_md5="same", asset_count=2)
    session.add(group)
    session.flush()
    session.add_all(
        [
            DuplicateGroupAsset(group_id=group.id, asset_id=first.id),
            DuplicateGroupAsset(group_id=group.id, asset_id=second.id),
        ]
    )
    session.commit()

    groups = list_exact_duplicate_groups(session, thumbnail_base="/thumbs", limit=10)

    assert groups == [
        {
            "id": group.id,
            "hash_md5": "same",
            "asset_count": 2,
            "status": "pending",
            "assets": [
                {
                    "id": first.id,
                    "file_name": "a.jpg",
                    "current_path": "/library/a.jpg",
                    "file_size": 10,
                    "mtime": 1.0,
                    "hash_md5": "same",
                    "hash_phash": None,
                    "thumbnail_url": f"/thumbs/{first.id}.jpg",
                },
                {
                    "id": second.id,
                    "file_name": "b.jpg",
                    "current_path": "/library/b.jpg",
                    "file_size": 20,
                    "mtime": 2.0,
                    "hash_md5": "same",
                    "hash_phash": None,
                    "thumbnail_url": f"/thumbs/{second.id}.jpg",
                },
            ],
        }
    ]


def test_list_similar_groups_returns_member_assets(tmp_path):
    session = make_session(tmp_path)
    library_row = Library(name="Library", kind="local", root_path="/library")
    session.add(library_row)
    session.flush()
    first = Asset(
        library_id=library_row.id,
        original_path="/library/a.jpg",
        current_path="/library/a.jpg",
        file_name="a.jpg",
        file_ext=".jpg",
        file_size=10,
        mtime=1.0,
        hash_phash="ffff0000ffff0000",
    )
    second = Asset(
        library_id=library_row.id,
        original_path="/library/b.jpg",
        current_path="/library/b.jpg",
        file_name="b.jpg",
        file_ext=".jpg",
        file_size=20,
        mtime=2.0,
        hash_phash="ffff0000ffff0001",
    )
    session.add_all([first, second])
    session.flush()
    group = SimilarGroup(representative_phash="ffff0000ffff0000", asset_count=2, threshold=6)
    session.add(group)
    session.flush()
    session.add_all(
        [
            SimilarGroupAsset(group_id=group.id, asset_id=first.id),
            SimilarGroupAsset(group_id=group.id, asset_id=second.id),
        ]
    )
    session.commit()

    groups = list_similar_groups(session, thumbnail_base="/thumbs", limit=10)

    assert groups[0]["id"] == group.id
    assert groups[0]["representative_phash"] == "ffff0000ffff0000"
    assert [row["id"] for row in groups[0]["assets"]] == [first.id, second.id]


def test_list_archive_anomalies_returns_risk_events_and_candidate_context(tmp_path):
    session = make_session(tmp_path)
    library_row = Library(name="Library", kind="local", root_path="/library")
    session.add(library_row)
    session.flush()
    candidate = SeriesCandidate(
        library_id=library_row.id,
        source_root="/library/紧急企划/紧急企划 - 见希-JK-R18 [85P1V1.32G]",
        title="紧急企划 - 见希-JK-R18 [85P1V1.32G]",
        status="pending_review",
    )
    session.add(candidate)
    session.flush()
    planning = ArchivePlanningRecord(
        candidate_id=candidate.id,
        source_root=candidate.source_root,
        rule_plan_json="{}",
        ai_plan_json="{}",
        final_plan_json='{"title":"紧急企划 - 见希-JK-R18 [85P1V1.32G]"}',
        decision_type="manual_review",
        rule_score=0.9,
        ai_score=0.9,
        risk_score=1.0,
        decision_reason="r18 suspected",
    )
    session.add(planning)
    session.flush()
    session.add(
        ArchiveRiskEvent(
            planning_record_id=planning.id,
            event_type="r18_suspected",
            severity="warning",
            details_json='{"source":"ai"}',
        )
    )
    session.commit()

    items = list_archive_anomalies(session=session, limit=10)

    assert items[0]["event_type"] == "r18_suspected"
    assert items[0]["candidate"]["source_root"].endswith("R18 [85P1V1.32G]")
    assert items[0]["decision_type"] == "manual_review"


def test_list_archive_execution_ledger_returns_execution_and_rollback_state(tmp_path):
    session = make_session(tmp_path)
    library_row = Library(name="Library", kind="local", root_path="/library")
    session.add(library_row)
    session.flush()
    candidate = SeriesCandidate(library_id=library_row.id, source_root="/library/set", title="set", status="confirmed")
    session.add(candidate)
    session.flush()
    planning = ArchivePlanningRecord(
        candidate_id=candidate.id,
        source_root=candidate.source_root,
        rule_plan_json="{}",
        ai_plan_json="{}",
        final_plan_json='{"title":"set"}',
        decision_type="auto_apply",
        rule_score=0.95,
        ai_score=0.93,
        risk_score=0.0,
        decision_reason="agreed",
    )
    session.add(planning)
    session.flush()
    session.add(
        ArchiveExecutionRecord(
            planning_record_id=planning.id,
            operation_type="archive_move",
            source_path="/library/set/001.jpg",
            target_path="/nas/set/001.jpg",
            status="done",
        )
    )
    session.commit()

    items = list_archive_execution_ledger(session=session, limit=10)

    assert items[0]["status"] == "done"
    assert items[0]["decision_type"] == "auto_apply"
    assert items[0]["source_path"] == "/library/set/001.jpg"


def test_get_archive_review_overview_summarizes_auto_archive_state(tmp_path):
    session = make_session(tmp_path)
    library_row = Library(name="Library", kind="local", root_path="/library")
    session.add(library_row)
    session.flush()
    candidate = SeriesCandidate(library_id=library_row.id, source_root="/library/set", title="set", status="confirmed")
    session.add(candidate)
    session.flush()
    planning = ArchivePlanningRecord(
        candidate_id=candidate.id,
        source_root=candidate.source_root,
        rule_plan_json="{}",
        ai_plan_json="{}",
        final_plan_json='{"title":"set"}',
        decision_type="auto_apply",
        rule_score=0.95,
        ai_score=0.93,
        risk_score=0.0,
        decision_reason="agreed",
    )
    session.add(planning)
    session.flush()
    session.add(
        ArchiveExecutionRecord(
            planning_record_id=planning.id,
            operation_type="archive_move",
            source_path="/library/set/001.jpg",
            target_path="/nas/set/001.jpg",
            status="done",
        )
    )
    session.commit()

    summary = get_archive_review_overview(session=session)

    assert summary["planning"]["auto_apply"] == 1
    assert summary["executions"]["done"] == 1
    assert summary["risk_events"] == 0


def test_list_archive_sampling_queue_returns_auto_apply_sampled_items(tmp_path):
    session = make_session(tmp_path)
    library_row = Library(name="Library", kind="local", root_path="/library")
    session.add(library_row)
    session.flush()
    candidate = SeriesCandidate(library_id=library_row.id, source_root="/library/set", title="set", status="confirmed")
    session.add(candidate)
    session.flush()
    planning = ArchivePlanningRecord(
        candidate_id=candidate.id,
        source_root=candidate.source_root,
        rule_plan_json="{}",
        ai_plan_json="{}",
        final_plan_json='{"title":"set"}',
        decision_type="auto_apply_sampled",
        rule_score=0.95,
        ai_score=0.85,
        risk_score=0.25,
        decision_reason="sample review recommended",
    )
    session.add(planning)
    session.flush()
    session.add(
        ArchiveRiskEvent(
            planning_record_id=planning.id,
            event_type="sample_review_recommended",
            severity="warning",
            details_json='{"reason":"title difference"}',
        )
    )
    session.commit()

    items = list_archive_sampling_queue(session=session, limit=10)

    assert items[0]["decision_type"] == "auto_apply_sampled"
    assert items[0]["candidate"]["id"] == candidate.id
