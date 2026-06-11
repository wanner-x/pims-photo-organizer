from collections.abc import Generator

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from pims_v1.db import Base, SessionLocal, engine
from pims_v1.services.review_service import list_exact_duplicate_groups, list_similar_groups

router = APIRouter(prefix="/review", tags=["review"])


def get_session() -> Generator[Session]:
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@router.get("/duplicates/exact")
def list_exact_duplicates(
    limit: int = 20,
    thumbnail_base: str = "/thumbnails",
    session: Session = Depends(get_session),
) -> dict[str, list]:
    return {
        "items": list_exact_duplicate_groups(
            session=session,
            thumbnail_base=thumbnail_base,
            limit=limit,
        )
    }


@router.get("/similar")
def list_similar(
    limit: int = 20,
    thumbnail_base: str = "/thumbnails",
    session: Session = Depends(get_session),
) -> dict[str, list]:
    return {
        "items": list_similar_groups(
            session=session,
            thumbnail_base=thumbnail_base,
            limit=limit,
        )
    }
