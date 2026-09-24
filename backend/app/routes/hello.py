"""The route that proves the api block is alive without any other block."""

from fastapi import APIRouter

from ..config import settings

router = APIRouter()


@router.get("/api/hello")
async def hello() -> dict:
    return {"message": f"hello from {settings.app_name}"}
