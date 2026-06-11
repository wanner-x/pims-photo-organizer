from fastapi import APIRouter

router = APIRouter(prefix="/libraries", tags=["libraries"])


@router.get("")
def list_libraries() -> dict[str, list]:
    return {"items": []}
