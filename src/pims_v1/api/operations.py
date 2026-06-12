from collections.abc import Generator

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from pims_v1.config import settings
from pims_v1.db import SessionLocal, ensure_database_schema, engine
from pims_v1.services.operation_plan_service import (
    confirm_operation_batch,
    count_batch_operations,
    exclude_operation,
    execute_confirmed_batch,
    list_batch_operations,
    list_operation_batches,
)

router = APIRouter(prefix="/operations", tags=["operations"])


def get_session() -> Generator[Session]:
    ensure_database_schema(engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def require_api_token(x_pims_api_token: str | None = Header(default=None)) -> None:
    if settings.api_token and x_pims_api_token != settings.api_token:
        raise HTTPException(status_code=401, detail="Invalid or missing API token")


@router.get("/batches")
def list_batches(session: Session = Depends(get_session)) -> dict[str, list]:
    return {"items": list_operation_batches(session)}


@router.get("/batches/{batch_id}/operations")
def list_operations_for_batch(
    batch_id: int,
    status: str | None = None,
    limit: int = 200,
    offset: int = 0,
    session: Session = Depends(get_session),
) -> dict[str, object]:
    operations = list_batch_operations(
        session=session,
        batch_id=batch_id,
        status=status,
        limit=limit,
        offset=offset,
    )
    return {
        "items": operations,
        "total": count_batch_operations(
            session=session,
            batch_id=batch_id,
            status=status,
        ),
        "limit": limit,
        "offset": offset,
    }


@router.post("/batches/{batch_id}/confirm")
def confirm_batch(
    batch_id: int,
    session: Session = Depends(get_session),
    _: None = Depends(require_api_token),
) -> dict:
    try:
        return confirm_operation_batch(session=session, batch_id=batch_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/batches/{batch_id}/execute")
def execute_batch(
    batch_id: int,
    session: Session = Depends(get_session),
    _: None = Depends(require_api_token),
) -> dict:
    try:
        return execute_confirmed_batch(
            session=session,
            batch_id=batch_id,
            quarantine_root=settings.quarantine_root,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{operation_id}/exclude")
def exclude_planned_operation(
    operation_id: int,
    session: Session = Depends(get_session),
    _: None = Depends(require_api_token),
) -> dict:
    try:
        return exclude_operation(session=session, operation_id=operation_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
