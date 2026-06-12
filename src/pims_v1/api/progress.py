from collections.abc import Generator

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from pims_v1.db import Base, SessionLocal, engine
from pims_v1.services.progress_service import review_progress_summary

router = APIRouter(prefix="/progress", tags=["progress"])


def get_session() -> Generator[Session]:
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@router.get("/summary")
def progress_summary(session: Session = Depends(get_session)) -> dict[str, object]:
    return review_progress_summary(session)
