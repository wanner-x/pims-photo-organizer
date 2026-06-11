from collections.abc import Generator

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from pims_v1.db import Base, SessionLocal, engine
from pims_v1.services.operation_plan_service import (
    confirm_operation_batch,
    execute_confirmed_batch,
    list_operation_batches,
)

router = APIRouter(prefix="/operations", tags=["operations"])


def get_session() -> Generator[Session]:
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@router.get("/batches")
def list_batches(session: Session = Depends(get_session)) -> dict[str, list]:
    return {"items": list_operation_batches(session)}


@router.post("/batches/{batch_id}/confirm")
def confirm_batch(batch_id: int, session: Session = Depends(get_session)) -> dict:
    try:
        return confirm_operation_batch(session=session, batch_id=batch_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/batches/{batch_id}/execute")
def execute_batch(
    batch_id: int,
    quarantine_root: str,
    session: Session = Depends(get_session),
) -> dict:
    try:
        return execute_confirmed_batch(
            session=session,
            batch_id=batch_id,
            quarantine_root=quarantine_root,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
