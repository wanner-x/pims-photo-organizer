from fastapi import APIRouter

router = APIRouter(prefix="/review", tags=["review"])


@router.get("/duplicates/exact")
def list_exact_duplicates() -> dict[str, list]:
    return {"items": []}
