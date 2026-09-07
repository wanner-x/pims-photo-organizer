from datetime import UTC, datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from pims_v1.db import Base
from pims_v1.models import asset, duplicate, library, operation, processing, review, series
from pims_v1.models.processing import ProcessingTask
from pims_v1.services.task_service import (
    claim_next_task,
    complete_task,
    enqueue_task,
    fail_task,
    list_tasks,
    recover_stale_tasks,
    reset_failed_tasks,
)
from pims_v1.services.task_service import recover_stale_status


def make_session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}", future=True)
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    return session_factory()


def utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def test_recover_stale_running_tasks():
    task = {"status": "running", "heartbeat_age_seconds": 1200}

    recovered = recover_stale_status(task, stale_after_seconds=300)

    assert recovered["status"] == "pending"
    assert recovered["attempts"] == 1


def test_enqueue_task_is_idempotent_for_active_subject(tmp_path):
    session = make_session(tmp_path)

    first = enqueue_task(session, "hash_md5", "asset", 1)
    second = enqueue_task(session, "hash_md5", "asset", 1)

    assert first.id == second.id
    assert session.query(ProcessingTask).count() == 1


def test_claim_next_task_marks_pending_task_running(tmp_path):
    session = make_session(tmp_path)
    task = enqueue_task(session, "hash_md5", "asset", 1)

    claimed = claim_next_task(session, task_type="hash_md5")

    assert claimed is not None
    assert claimed.id == task.id
    assert claimed.status == "running"
    assert claimed.attempts == 1
    assert claimed.heartbeat_at is not None


def test_recover_stale_tasks_returns_old_running_tasks_to_pending(tmp_path):
    session = make_session(tmp_path)
    task = enqueue_task(session, "hash_md5", "asset", 1)
    task.status = "running"
    task.attempts = 2
    task.heartbeat_at = utc_now() - timedelta(minutes=30)
    session.commit()

    summary = recover_stale_tasks(
        session,
        stale_after_seconds=300,
        now=utc_now(),
    )

    session.refresh(task)
    assert summary == {"recovered": 1}
    assert task.status == "pending"
    assert task.attempts == 3


def test_complete_and_fail_task_update_final_status(tmp_path):
    session = make_session(tmp_path)
    completed = enqueue_task(session, "hash_md5", "asset", 1)
    failed = enqueue_task(session, "hash_md5", "asset", 2)

    complete_task(session, completed.id)
    fail_task(session, failed.id, "missing file")

    session.refresh(completed)
    session.refresh(failed)
    assert completed.status == "completed"
    assert failed.status == "failed"
    assert failed.last_error == "missing file"


def test_reset_failed_tasks_requeues_only_failed(tmp_path):
    session = make_session(tmp_path)
    failed_phash = enqueue_task(session, "hash_phash", "asset", 1)
    failed_phash.status = "failed"
    failed_phash.last_error = "phash failed: too many pixels"
    failed_md5 = enqueue_task(session, "hash_md5", "asset", 2)
    failed_md5.status = "failed"
    completed = enqueue_task(session, "hash_phash", "asset", 3)
    completed.status = "completed"
    session.commit()

    summary = reset_failed_tasks(session, task_type="hash_phash")

    session.refresh(failed_phash)
    session.refresh(failed_md5)
    session.refresh(completed)
    assert summary == {"reset": 1}
    assert failed_phash.status == "pending"
    assert failed_phash.last_error is None
    assert failed_md5.status == "failed"
    assert completed.status == "completed"


def test_reset_failed_tasks_without_type_resets_all(tmp_path):
    session = make_session(tmp_path)
    first = enqueue_task(session, "hash_phash", "asset", 1)
    first.status = "failed"
    second = enqueue_task(session, "hash_md5", "asset", 2)
    second.status = "failed"
    session.commit()

    summary = reset_failed_tasks(session)

    assert summary == {"reset": 2}


def test_list_tasks_filters_by_status(tmp_path):
    session = make_session(tmp_path)
    enqueue_task(session, "hash_md5", "asset", 1)
    running = enqueue_task(session, "hash_md5", "asset", 2)
    running.status = "running"
    session.commit()

    tasks = list_tasks(session, status="running")

    assert len(tasks) == 1
    assert tasks[0]["id"] == running.id
    assert tasks[0]["status"] == "running"
