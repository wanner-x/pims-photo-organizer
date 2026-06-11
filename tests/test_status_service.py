from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from pims_v1.db import Base
from pims_v1.models import asset, duplicate, library, operation, processing, review, series
from pims_v1.models.asset import Asset
from pims_v1.models.duplicate import DuplicateGroup
from pims_v1.models.library import Library
from pims_v1.models.processing import ProcessingTask
from pims_v1.models.review import ReviewItem
from pims_v1.models.series import SeriesCandidate
from pims_v1.services.status_service import database_status


def make_session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}", future=True)
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    return session_factory()


def test_database_status_counts_core_entities(tmp_path):
    session = make_session(tmp_path)
    library_row = Library(name="Library", kind="local", root_path="/library")
    session.add(library_row)
    session.flush()
    session.add(
        Asset(
            library_id=library_row.id,
            original_path="/library/a.jpg",
            current_path="/library/a.jpg",
            file_name="a.jpg",
            file_ext=".jpg",
            file_size=1,
            mtime=1.0,
            hash_md5="abc",
            hash_phash="ffff0000ffff0000",
        )
    )
    session.add(
        Asset(
            library_id=library_row.id,
            original_path="/library/b.jpg",
            current_path="/library/b.jpg",
            file_name="b.jpg",
            file_ext=".jpg",
            file_size=1,
            mtime=1.0,
        )
    )
    session.add(DuplicateGroup(hash_md5="abc", asset_count=2))
    session.add(SeriesCandidate(library_id=library_row.id, source_root="/library", title="library"))
    session.add(ReviewItem(item_type="series_confirm", subject_id=1))
    session.add(
        ProcessingTask(
            task_type="hash_md5",
            subject_type="asset",
            subject_id=1,
            status="pending",
        )
    )
    session.add(
        ProcessingTask(
            task_type="hash_md5",
            subject_type="asset",
            subject_id=2,
            status="failed",
        )
    )
    session.commit()

    status = database_status(session)

    assert status == {
        "libraries": 1,
        "assets": 2,
        "assets_with_md5": 1,
        "assets_with_phash": 1,
        "duplicate_groups": 1,
        "series_candidates": 1,
        "review_items_pending": 1,
        "tasks_pending": 1,
        "tasks_running": 0,
        "tasks_failed": 1,
        "tasks_completed": 0,
    }
