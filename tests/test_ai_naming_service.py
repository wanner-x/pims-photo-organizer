from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from pims_v1.db import Base
from pims_v1.models import asset, duplicate, library, operation, processing, review, series
from pims_v1.models.asset import Asset
from pims_v1.models.library import Library
from pims_v1.models.series import SeriesCandidate, SeriesCandidateAsset, SeriesSuggestion
from pims_v1.services.ai_naming_service import (
    build_series_title_prompt,
    build_series_organization_prompt,
    suggest_series_organization,
    suggest_series_title,
)


class FakeNamingClient:
    def __init__(self) -> None:
        self.messages = []

    def chat(self, messages):
        self.messages = messages
        return "Clean Title"


class FakeOrganizationClient:
    def __init__(self) -> None:
        self.messages = []

    def chat(self, messages):
        self.messages = messages
        return '{"title":"清晨海边写真","category":"写真合集","confidence":0.82}'


def make_session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}", future=True)
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    return session_factory()


def test_build_series_title_prompt_uses_source_and_sample_names():
    prompt = build_series_title_prompt(
        source_root="/library/model-a/set-01",
        file_names=["001.jpg", "002.jpg"],
    )

    assert "set-01" in prompt
    assert "001.jpg" in prompt
    assert "002.jpg" in prompt


def test_suggest_series_title_updates_candidate_with_ai_title(tmp_path):
    session = make_session(tmp_path)
    library_row = Library(name="Library", kind="local", root_path="/library")
    session.add(library_row)
    session.flush()
    asset_row = Asset(
        library_id=library_row.id,
        original_path="/library/set/a.jpg",
        current_path="/library/set/a.jpg",
        file_name="a.jpg",
        file_ext=".jpg",
        file_size=1,
        mtime=1.0,
    )
    session.add(asset_row)
    session.flush()
    candidate = SeriesCandidate(library_id=library_row.id, source_root="/library/set")
    session.add(candidate)
    session.flush()
    session.add(SeriesCandidateAsset(candidate_id=candidate.id, asset_id=asset_row.id))
    session.commit()
    client = FakeNamingClient()

    result = suggest_series_title(session=session, candidate_id=candidate.id, client=client)

    session.refresh(candidate)
    assert result == {"candidate_id": candidate.id, "title": "Clean Title"}
    assert candidate.title == "Clean Title"
    assert candidate.status == "ai_suggested"
    assert candidate.confidence == 0.6
    assert "a.jpg" in client.messages[0]["content"]


def test_build_series_organization_prompt_requests_reviewable_json():
    prompt = build_series_organization_prompt(
        source_root="/library/model-a/set-01",
        file_names=["001.jpg", "002.jpg"],
    )

    assert "set-01" in prompt
    assert "001.jpg" in prompt
    assert "title" in prompt
    assert "category" in prompt


def test_suggest_series_organization_creates_review_suggestion(tmp_path):
    session = make_session(tmp_path)
    library_row = Library(name="Library", kind="local", root_path="/library")
    session.add(library_row)
    session.flush()
    asset_row = Asset(
        library_id=library_row.id,
        original_path="/library/set/a.jpg",
        current_path="/library/set/a.jpg",
        file_name="a.jpg",
        file_ext=".jpg",
        file_size=1,
        mtime=1.0,
    )
    session.add(asset_row)
    session.flush()
    candidate = SeriesCandidate(library_id=library_row.id, source_root="/library/set")
    session.add(candidate)
    session.flush()
    session.add(SeriesCandidateAsset(candidate_id=candidate.id, asset_id=asset_row.id))
    session.commit()
    client = FakeOrganizationClient()

    result = suggest_series_organization(session=session, candidate_id=candidate.id, client=client)

    suggestion = session.query(SeriesSuggestion).one()
    session.refresh(candidate)
    assert result == {
        "candidate_id": candidate.id,
        "suggestion_id": suggestion.id,
        "title": "清晨海边写真",
        "category": "写真合集",
        "confidence": 0.82,
    }
    assert suggestion.status == "pending_review"
    assert suggestion.suggested_title == "清晨海边写真"
    assert suggestion.suggested_category == "写真合集"
    assert candidate.status == "ai_suggested"
    assert candidate.title == "清晨海边写真"
