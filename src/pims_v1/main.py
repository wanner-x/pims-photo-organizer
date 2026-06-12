from pathlib import Path

from fastapi import FastAPI
from fastapi import HTTPException
from fastapi.responses import FileResponse

from pims_v1.api.libraries import router as libraries_router
from pims_v1.api.operations import router as operations_router
from pims_v1.api.review import router as review_router
from pims_v1.api.review_ui import router as review_ui_router
from pims_v1.api.tasks import router as tasks_router
from pims_v1.config import settings

app = FastAPI(title="PIMS V1")
app.include_router(libraries_router)
app.include_router(review_router)
app.include_router(operations_router)
app.include_router(tasks_router)
app.include_router(review_ui_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/thumbnails/{asset_id}.jpg")
def thumbnail(asset_id: int) -> FileResponse:
    path = Path(settings.cache_root) / "thumbnails" / f"{asset_id}.jpg"
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="Thumbnail not found")
    return FileResponse(path, media_type="image/jpeg")
