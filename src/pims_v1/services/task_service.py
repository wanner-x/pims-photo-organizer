from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from pims_v1.models.processing import ProcessingTask


def recover_stale_status(task: dict, stale_after_seconds: int) -> dict:
    if task["status"] == "running" and task["heartbeat_age_seconds"] > stale_after_seconds:
        return {"status": "pending", "attempts": task.get("attempts", 0) + 1}
    return {"status": task["status"], "attempts": task.get("attempts", 0)}


ACTIVE_STATUSES = ("pending", "running")


def _utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def enqueue_task(
    session: Session,
    task_type: str,
    subject_type: str,
    subject_id: int,
) -> ProcessingTask:
    existing = (
        session.query(ProcessingTask)
        .filter(
            ProcessingTask.task_type == task_type,
            ProcessingTask.subject_type == subject_type,
            ProcessingTask.subject_id == subject_id,
            ProcessingTask.status.in_(ACTIVE_STATUSES),
        )
        .order_by(ProcessingTask.id)
        .first()
    )
    if existing is not None:
        return existing

    task = ProcessingTask(
        task_type=task_type,
        subject_type=subject_type,
        subject_id=subject_id,
        status="pending",
    )
    session.add(task)
    session.commit()
    return task


def claim_next_task(session: Session, task_type: str | None = None) -> ProcessingTask | None:
    query = session.query(ProcessingTask).filter(ProcessingTask.status == "pending")
    if task_type is not None:
        query = query.filter(ProcessingTask.task_type == task_type)
    task = query.order_by(ProcessingTask.id).first()
    if task is None:
        return None

    task.status = "running"
    task.attempts += 1
    task.heartbeat_at = _utc_now()
    task.last_error = None
    session.commit()
    return task


def complete_task(session: Session, task_id: int) -> ProcessingTask:
    task = _get_task_or_raise(session, task_id)
    task.status = "completed"
    task.heartbeat_at = _utc_now()
    task.last_error = None
    session.commit()
    return task


def fail_task(session: Session, task_id: int, error: str) -> ProcessingTask:
    task = _get_task_or_raise(session, task_id)
    task.status = "failed"
    task.heartbeat_at = _utc_now()
    task.last_error = error[:2048]
    session.commit()
    return task


def recover_stale_tasks(
    session: Session,
    stale_after_seconds: int,
    now: datetime | None = None,
) -> dict[str, int]:
    now = now or _utc_now()
    cutoff = now - timedelta(seconds=stale_after_seconds)
    tasks = (
        session.query(ProcessingTask)
        .filter(
            ProcessingTask.status == "running",
            ProcessingTask.heartbeat_at.is_not(None),
            ProcessingTask.heartbeat_at < cutoff,
        )
        .order_by(ProcessingTask.id)
        .all()
    )
    for task in tasks:
        task.status = "pending"
        task.attempts += 1
    session.commit()
    return {"recovered": len(tasks)}


def list_tasks(
    session: Session,
    status: str | None = None,
    limit: int = 100,
) -> list[dict[str, int | str | None]]:
    query = session.query(ProcessingTask)
    if status is not None:
        query = query.filter(ProcessingTask.status == status)
    tasks = query.order_by(ProcessingTask.id).limit(limit).all()
    return [
        {
            "id": task.id,
            "task_type": task.task_type,
            "subject_type": task.subject_type,
            "subject_id": task.subject_id,
            "status": task.status,
            "attempts": task.attempts,
            "last_error": task.last_error,
        }
        for task in tasks
    ]


def _get_task_or_raise(session: Session, task_id: int) -> ProcessingTask:
    task = session.get(ProcessingTask, task_id)
    if task is None:
        raise ValueError(f"Processing task not found: {task_id}")
    return task
