from fastapi import APIRouter

router = APIRouter(prefix="/operations", tags=["operations"])


@router.get("/batches")
def list_batches() -> dict[str, list]:
    return {"items": []}
