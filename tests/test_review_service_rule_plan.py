from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from pims_v1.db import Base
from pims_v1.models import archive_decision, asset, duplicate, library, operation, processing, review, series
from pims_v1.models.asset import Asset
from pims_v1.models.library import Library
from pims_v1.models.series import SeriesCandidate, SeriesCandidateAsset
from pims_v1.services.review_service import list_series_review_candidates


def make_session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}", future=True)
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    return session_factory()


def test_list_series_review_candidates_can_include_rule_plan(tmp_path):
    session = make_session(tmp_path)
    library_row = Library(name="Library", kind="local", root_path="/library")
    session.add(library_row)
    session.flush()
    asset_row = Asset(
        library_id=library_row.id,
        original_path="/library/[IMISS] 2025.08.27 VOL.800 Sabrina [86+1P]/001.jpg",
        current_path="/library/[IMISS] 2025.08.27 VOL.800 Sabrina [86+1P]/001.jpg",
        file_name="001.jpg",
        file_ext=".jpg",
        file_size=1,
        mtime=1.0,
    )
    session.add(asset_row)
    session.flush()
    candidate = SeriesCandidate(
        library_id=library_row.id,
        source_root="/library/[IMISS] 2025.08.27 VOL.800 Sabrina [86+1P]",
        title="[IMISS] 2025.08.27 VOL.800 Sabrina [86+1P]",
    )
    session.add(candidate)
    session.flush()
    session.add(SeriesCandidateAsset(candidate_id=candidate.id, asset_id=asset_row.id))
    session.commit()

    items = list_series_review_candidates(session, include_rule_plan=True)

    assert items[0]["rule_plan"]["archive_category"] == "IMISS"
    assert items[0]["rule_plan"]["archive_title"] == "[IMISS] 2025.08.27 VOL.800 Sabrina [86+1P]"
    assert items[0]["rule_plan"]["metadata"]["metadata_tokens"] == ["VOL.800", "86+1P"]
