from collections.abc import Generator

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from pims_v1.config import settings
from pims_v1.db import SessionLocal
from pims_v1.services.archive_decision_service import auto_archive_candidate, rollback_archive_execution
from pims_v1.services.ai_naming_service import suggest_series_organization
from pims_v1.services.deepseek_client import DeepSeekClient
from pims_v1.services.review_service import (
    get_archive_review_overview,
    list_archive_anomalies,
    list_archive_execution_ledger,
    list_archive_sampling_queue,
    list_exact_duplicate_groups,
    list_series_review_candidates,
    list_similar_groups,
)
from pims_v1.services.series_moderation_service import review_series_r18
from pims_v1.services.series_confirm_service import confirm_series_suggestion
from pims_v1.services.visual_moderation_service import build_visual_moderation_client

router = APIRouter(prefix="/review", tags=["review"])


def get_session() -> Generator[Session]:
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
    filter: str | None = None,
    session: Session = Depends(get_session),
) -> dict[str, list]:
    return {
        "items": list_series_review_candidates(
            session=session,
            limit=limit,
            status=status,
            review_filter=filter,
            include_rule_plan=True,
        )
    }


@router.get("/archive/overview")
def archive_review_overview(session: Session = Depends(get_session)) -> dict:
    return get_archive_review_overview(session=session)


@router.get("/archive/anomalies")
def archive_anomalies(limit: int = 20, session: Session = Depends(get_session)) -> dict[str, list]:
    return {"items": list_archive_anomalies(session=session, limit=limit)}


@router.get("/archive/sampling")
def archive_sampling(limit: int = 20, session: Session = Depends(get_session)) -> dict[str, list]:
    return {"items": list_archive_sampling_queue(session=session, limit=limit)}


@router.get("/archive/executions")
def archive_execution_ledger(limit: int = 20, session: Session = Depends(get_session)) -> dict[str, list]:
    return {"items": list_archive_execution_ledger(session=session, limit=limit)}


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
            reasoning_effort=settings.deepseek_reasoning_effort,
            thinking_enabled=settings.deepseek_thinking_enabled,
        )
        return suggest_series_organization(
            session=session,
            candidate_id=candidate_id,
            client=client,
            archive_root=settings.keep_root,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/series/{candidate_id}/auto-archive")
def auto_archive_series(
    candidate_id: int,
    session: Session = Depends(get_session),
    _: None = Depends(require_api_token),
) -> dict:
    try:
        client = DeepSeekClient(
            api_key=settings.deepseek_api_key,
            base_url=settings.deepseek_base_url,
            model=settings.deepseek_model,
            reasoning_effort=settings.deepseek_reasoning_effort,
            thinking_enabled=settings.deepseek_thinking_enabled,
        )
        archive_root = settings.keep_root
        if not archive_root:
            raise ValueError("PIMS_KEEP_ROOT is required")
        return auto_archive_candidate(
            session=session,
            candidate_id=candidate_id,
            archive_root=archive_root,
            client=client,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/series/{candidate_id}/scan-r18")
def scan_series_r18(
    candidate_id: int,
    session: Session = Depends(get_session),
    _: None = Depends(require_api_token),
) -> dict:
    try:
        provider = build_visual_moderation_client(settings.r18_provider)
        return review_series_r18(
            session=session,
            candidate_id=candidate_id,
            provider=provider,
            mode="manual",
            sample_limit=settings.r18_sample_limit,
            high_threshold=settings.r18_high_threshold,
            review_threshold=settings.r18_review_threshold,
        )
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


@router.post("/archive/executions/{execution_id}/rollback")
def rollback_archive_execution_route(
    execution_id: int,
    session: Session = Depends(get_session),
    _: None = Depends(require_api_token),
) -> dict:
    try:
        return rollback_archive_execution(
            session=session,
            execution_id=execution_id,
            operator="review_api",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
