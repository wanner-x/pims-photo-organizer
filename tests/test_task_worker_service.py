from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from pims_v1.db import Base
from pims_v1.models import asset, duplicate, library, operation, processing, review, series
from pims_v1.models.asset import Asset
from pims_v1.models.library import Library
from pims_v1.models.processing import ProcessingTask
from pims_v1.services.task_service import enqueue_task
from pims_v1.services.task_worker_service import process_md5_tasks


def make_session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}", future=True)
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    return session_factory()


def add_asset(session, path, size: int | None = None):
    library_row = session.query(Library).filter(Library.root_path == str(path.parent)).first()
    if library_row is None:
        library_row = Library(name="Photos", kind="local", root_path=str(path.parent))
        session.add(library_row)
        session.flush()
    asset_row = Asset(
        library_id=library_row.id,
        original_path=str(path),
        current_path=str(path),
        file_name=path.name,
        file_ext=path.suffix,
        file_size=size if size is not None else path.stat().st_size,
        mtime=1.0,
    )
    session.add(asset_row)
    session.flush()
    return asset_row


def test_process_md5_tasks_hashes_asset_and_completes_task(tmp_path):
    session = make_session(tmp_path)
    source = tmp_path / "a.jpg"
    source.write_bytes(b"hash-me")
    asset_row = add_asset(session, source)
    task = enqueue_task(session, "hash_md5", "asset", asset_row.id)

    summary = process_md5_tasks(session=session, limit=10)

    session.refresh(asset_row)
    session.refresh(task)
    assert summary == {"processed": 1, "failed": 0, "skipped_oversize": 0}
    assert asset_row.hash_md5 == "0b893466231ec15a31520cfb1f761f4f"
    assert asset_row.stage == "md5_done"
    assert task.status == "completed"


def test_process_md5_tasks_marks_missing_file_failed(tmp_path):
    session = make_session(tmp_path)
    source = tmp_path / "missing.jpg"
    source.write_bytes(b"exists-for-index")
    asset_row = add_asset(session, source)
    source.unlink()
    task = enqueue_task(session, "hash_md5", "asset", asset_row.id)

    summary = process_md5_tasks(session=session, limit=10)

    session.refresh(task)
    assert summary == {"processed": 0, "failed": 1, "skipped_oversize": 0}
    assert task.status == "failed"
    assert "missing file" in task.last_error


def test_process_md5_tasks_completes_oversize_without_hashing(tmp_path):
    session = make_session(tmp_path)
    source = tmp_path / "large.jpg"
    source.write_bytes(b"large")
    asset_row = add_asset(session, source, size=100)
    task = enqueue_task(session, "hash_md5", "asset", asset_row.id)

    summary = process_md5_tasks(session=session, limit=10, max_bytes=50)

    session.refresh(asset_row)
    session.refresh(task)
    assert summary == {"processed": 0, "failed": 0, "skipped_oversize": 1}
    assert asset_row.hash_md5 is None
    assert asset_row.stage == "md5_skipped_oversize"
    assert task.status == "completed"


def test_process_md5_tasks_respects_limit(tmp_path):
    session = make_session(tmp_path)
    for index in range(3):
        source = tmp_path / f"{index}.jpg"
        source.write_bytes(f"asset-{index}".encode("ascii"))
        asset_row = add_asset(session, source)
        enqueue_task(session, "hash_md5", "asset", asset_row.id)

    summary = process_md5_tasks(session=session, limit=2)

    completed = session.query(ProcessingTask).filter(ProcessingTask.status == "completed").count()
    pending = session.query(ProcessingTask).filter(ProcessingTask.status == "pending").count()
    assert summary == {"processed": 2, "failed": 0, "skipped_oversize": 0}
    assert completed == 2
    assert pending == 1
