from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from pims_v1.db import Base
from pims_v1.models import asset, duplicate, library, operation, processing, review, series
from pims_v1.models.asset import Asset
from pims_v1.models.library import Library
from pims_v1.services.progress_service import review_progress_summary


def make_session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}", future=True)
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    return session_factory()


def test_progress_phash_total_excludes_removed_assets(tmp_path):
    session = make_session(tmp_path)
    library_row = Library(name="Photos", kind="local", root_path=str(tmp_path))
    session.add(library_row)
    session.flush()
    session.add_all(
        [
            Asset(
                library_id=library_row.id,
                original_path="/library/active.jpg",
                current_path="/library/active.jpg",
                file_name="active.jpg",
                file_ext=".jpg",
                file_size=1,
                mtime=1.0,
                status="normal",
            ),
            Asset(
                library_id=library_row.id,
                original_path="/library/removed.jpg",
                current_path="/library/removed.jpg",
                file_name="removed.jpg",
                file_ext=".jpg",
                file_size=1,
                mtime=1.0,
                status="deleted",
            ),
            Asset(
                library_id=library_row.id,
                original_path="/library/quarantined.jpg",
                current_path="/library/quarantined.jpg",
                file_name="quarantined.jpg",
                file_ext=".jpg",
                file_size=1,
                mtime=1.0,
                status="quarantined",
            ),
            Asset(
                library_id=library_row.id,
                original_path="/library/invalid.jpg",
                current_path="/library/invalid.jpg",
                file_name="invalid.jpg",
                file_ext=".jpg",
                file_size=1,
                mtime=1.0,
                status="invalid_image",
            ),
        ]
    )
    session.commit()

    summary = review_progress_summary(session)

    assert summary["assets"]["phash_total"] == 1
