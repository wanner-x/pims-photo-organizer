from fastapi import FastAPI

from pims_v1.api.libraries import router as libraries_router
from pims_v1.api.operations import router as operations_router
from pims_v1.api.review import router as review_router

app = FastAPI(title="PIMS V1")
app.include_router(libraries_router)
app.include_router(review_router)
app.include_router(operations_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
