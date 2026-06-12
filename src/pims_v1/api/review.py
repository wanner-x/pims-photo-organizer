from collections.abc import Generator

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from pims_v1.config import settings
from pims_v1.db import Base, SessionLocal, engine
from pims_v1.services.ai_naming_service import suggest_series_organization
from pims_v1.services.deepseek_client import DeepSeekClient
from pims_v1.services.review_service import (
    list_exact_duplicate_groups,
    list_series_review_candidates,
    list_similar_groups,
)
from pims_v1.services.series_confirm_service import confirm_series_suggestion

router = APIRouter(prefix="/review", tags=["review"])


def get_session() -> Generator[Session]:
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


class ConfirmSeriesSuggestionRequest(BaseModel):
    title: str | None = None
    category: str | None = None
    archive_root: str | None = None


def require_api_token(x_pims_api_token: str | None = Header(default=None)) -> None:
    if settings.api_token and x_pims_api_token != settings.api_token:
        raise HTTPException(status_code=401, detail="Invalid or missing API token")


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


@router.get("/series")
def list_series_for_review(
    limit: int = 20,
    status: str | None = None,
    session: Session = Depends(get_session),
) -> dict[str, list]:
    return {"items": list_series_review_candidates(session=session, limit=limit, status=status)}


@router.post("/series/{candidate_id}/suggest-ai")
def suggest_series_ai(
    candidate_id: int,
    session: Session = Depends(get_session),
    _: None = Depends(require_api_token),
) -> dict:
    try:
        client = DeepSeekClient(
            api_key=settings.deepseek_api_key,
            base_url=settings.deepseek_base_url,
            model=settings.deepseek_model,
        )
        return suggest_series_organization(session=session, candidate_id=candidate_id, client=client)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/series-suggestions/{suggestion_id}/confirm")
def confirm_series_ai_suggestion(
    suggestion_id: int,
    payload: ConfirmSeriesSuggestionRequest | None = None,
    session: Session = Depends(get_session),
    _: None = Depends(require_api_token),
) -> dict:
    payload = payload or ConfirmSeriesSuggestionRequest()
    archive_root = payload.archive_root or settings.keep_root
    if not archive_root:
        raise HTTPException(status_code=400, detail="PIMS_KEEP_ROOT or archive_root is required")
    try:
        return confirm_series_suggestion(
            session=session,
            suggestion_id=suggestion_id,
            archive_root=archive_root,
            title=payload.title,
            category=payload.category,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
