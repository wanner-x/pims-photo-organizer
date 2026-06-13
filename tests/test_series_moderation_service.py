from pathlib import Path

from PIL import Image
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from pims_v1.db import Base
from pims_v1.models import asset, library, series
from pims_v1.models.library import Library
from pims_v1.models.series import SeriesCandidate, SeriesCandidateAsset, SeriesSuggestion
from pims_v1.models.series_moderation import SeriesModerationRun, SeriesModerationSample
from pims_v1.services.series_moderation_service import (
    review_series_r18,
    select_candidate_image_samples,
)


class StaticVisualModerationClient:
    def __init__(self, payloads: list[dict[str, object]]) -> None:
        self.payloads = list(payloads)
        self.provider_name = "static"

    def moderate_image(self, path: Path) -> dict[str, object]:
        if not self.payloads:
            raise AssertionError("No moderation payload left")
        payload = dict(self.payloads.pop(0))
        payload.setdefault("provider", self.provider_name)
        return payload


def make_session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}", future=True)
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    return session_factory()


def build_candidate_with_images(tmp_path, image_count: int = 10):
    session = make_session(tmp_path)
    root = tmp_path / "library" / "set"
    root.mkdir(parents=True)
    library_row = Library(name="Photos", kind="local", root_path=str(tmp_path / "library"))
    session.add(library_row)
    session.flush()
    candidate = SeriesCandidate(
        library_id=library_row.id,
        source_root=str(root),
        title="set",
        status="pending",
    )
    session.add(candidate)
    session.flush()
    for index in range(image_count):
        path = root / f"{index:03d}.jpg"
        Image.new("RGB", (32, 32), color=(220, 180, 160) if index % 2 else (40, 80, 180)).save(path)
        asset_row = asset.Asset(
            library_id=library_row.id,
            original_path=str(path),
            current_path=str(path),
            file_name=path.name,
            file_ext=path.suffix,
            file_size=path.stat().st_size,
            mtime=1.0 + index,
        )
        session.add(asset_row)
        session.flush()
        session.add(SeriesCandidateAsset(candidate_id=candidate.id, asset_id=asset_row.id, sort_order=index))
    session.commit()
    return session, candidate.id


def test_select_candidate_image_samples_balances_front_middle_and_tail(tmp_path):
    session, candidate_id = build_candidate_with_images(tmp_path, image_count=10)

    samples = select_candidate_image_samples(session=session, candidate_id=candidate_id, limit=7)

    assert len(samples) == 7
    assert samples[0].sort_order == 0
    assert samples[-1].sort_order == 9
    assert len({sample.asset_id for sample in samples}) == 7


def test_review_series_r18_marks_candidate_when_local_provider_returns_high_score(tmp_path):
    session, candidate_id = build_candidate_with_images(tmp_path, image_count=2)
    session.add(
        SeriesSuggestion(
            candidate_id=candidate_id,
            suggested_title="set",
            suggested_category="Alice",
            confidence=0.8,
            status="pending_review",
        )
    )
    session.commit()
    provider = StaticVisualModerationClient(
        [
            {"label": "safe", "score": 0.18, "reason": "low skin ratio"},
            {"label": "nsfw_suspected", "score": 0.91, "reason": "high skin ratio"},
        ]
    )

    result = review_series_r18(
        session=session,
        candidate_id=candidate_id,
        provider=provider,
        mode="manual",
        sample_limit=7,
        high_threshold=0.82,
        review_threshold=0.55,
    )

    suggestion = session.query(SeriesSuggestion).one()
    run_row = session.query(SeriesModerationRun).one()
    sample_rows = session.query(SeriesModerationSample).order_by(SeriesModerationSample.id).all()

    assert result["r18_label"] is True
    assert result["positive_samples"] == 1
    assert "visual_r18_suspected" in result["risk_flags"]
    assert result["provider"] == "static"
    assert suggestion.r18_label is True
    assert suggestion.r18_confidence == 0.91
    assert run_row.flagged_samples == 1
    assert len(sample_rows) == 2
