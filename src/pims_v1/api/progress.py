from collections.abc import Generator

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from pims_v1.config import settings
from pims_v1.db import SessionLocal, ensure_database_schema, engine
from pims_v1.services.log_service import latest_log_tail
from pims_v1.services.progress_service import review_progress_summary

router = APIRouter(prefix="/progress", tags=["progress"])


def get_session() -> Generator[Session]:
    ensure_database_schema(engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@router.get("/summary")
def progress_summary(session: Session = Depends(get_session)) -> dict[str, object]:
    return review_progress_summary(session)


@router.get("/logs/latest")
def latest_progress_log(lines: int = 80) -> dict[str, object]:
    return latest_log_tail(settings.logs_root, lines=lines)
