from collections.abc import Generator

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from pims_v1.db import SessionLocal, ensure_database_schema, engine
from pims_v1.services.task_service import list_tasks, recover_stale_tasks

router = APIRouter(prefix="/tasks", tags=["tasks"])


def get_session() -> Generator[Session]:
    ensure_database_schema(engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@router.get("")
def list_processing_tasks(
    status: str | None = None,
    limit: int = 100,
    session: Session = Depends(get_session),
) -> dict[str, list]:
    return {"items": list_tasks(session=session, status=status, limit=limit)}


@router.post("/recover")
def recover_processing_tasks(
    stale_after_seconds: int = 300,
    session: Session = Depends(get_session),
) -> dict[str, int]:
    return recover_stale_tasks(
        session=session,
        stale_after_seconds=stale_after_seconds,
    )
