import asyncio
from pathlib import Path
from contextlib import asynccontextmanager
from collections.abc import Generator

from fastapi import Depends, FastAPI, WebSocket, WebSocketDisconnect
from fastapi import HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from pims_v1.api.libraries import router as libraries_router
from pims_v1.api.operations import router as operations_router
from pims_v1.api.progress import router as progress_router
from pims_v1.api.review import router as review_router
from pims_v1.api.review_ui import router as review_ui_router
from pims_v1.api.tasks import router as tasks_router
from pims_v1.config import settings
from pims_v1.db import SessionLocal, ensure_database_schema, engine
from pims_v1.models.asset import Asset
from pims_v1.services.log_service import latest_log_tail
from pims_v1.services.progress_service import review_progress_summary


@asynccontextmanager
async def lifespan(_app: FastAPI):
    ensure_database_schema(engine)
    yield


app = FastAPI(title="PIMS V1", lifespan=lifespan)
app.include_router(libraries_router)
app.include_router(review_router)
app.include_router(operations_router)
app.include_router(tasks_router)
app.include_router(review_ui_router)
app.include_router(progress_router)


def get_session() -> Generator[Session]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/thumbnails/{asset_id}.jpg")
def thumbnail(asset_id: int) -> FileResponse:
    path = Path(settings.cache_root) / "thumbnails" / f"{asset_id}.jpg"
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="Thumbnail not found")
    return FileResponse(path, media_type="image/jpeg")


@app.get("/media/assets/{asset_id}")
def media_asset(asset_id: int, session: Session = Depends(get_session)) -> FileResponse:
    asset = session.get(Asset, asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail="Asset not found")
    path = Path(asset.current_path or asset.original_path)
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="Media file not found")
    return FileResponse(path)


def _progress_snapshot() -> dict[str, object]:
    session = SessionLocal()
    try:
        return {
            "type": "snapshot",
            "progress": review_progress_summary(session),
            "log": latest_log_tail(settings.logs_root, lines=80),
        }
    finally:
        session.close()


@app.websocket("/ws/progress")
async def progress_websocket(websocket: WebSocket) -> None:
    await websocket.accept()
    try:
        while True:
            try:
                payload = await asyncio.to_thread(_progress_snapshot)
            except Exception:
                payload = {
                    "type": "error",
                    "message": "自动刷新暂时失败，正在继续重试。",
                }
            await websocket.send_json(payload)
            await asyncio.sleep(5)
    except WebSocketDisconnect:
        return
