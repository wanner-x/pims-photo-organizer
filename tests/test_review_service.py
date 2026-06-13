from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from pims_v1.db import Base
from pims_v1.models import asset, duplicate, library, operation, processing, review, series
from pims_v1.models.asset import Asset
from pims_v1.models.duplicate import DuplicateGroup, DuplicateGroupAsset
from pims_v1.models.library import Library
from pims_v1.models.similar import SimilarGroup, SimilarGroupAsset
from pims_v1.models.series import SeriesCandidate, SeriesCandidateAsset, SeriesSuggestion
from pims_v1.services.review_service import (
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
