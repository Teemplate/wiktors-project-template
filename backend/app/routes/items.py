"""The example data route — present only when `api` and `postgres` both are.

This is what the deploy gate and the e2e suite check, because it is the
cheapest thing that proves the whole path works: config loaded, engine built,
migration applied, database reachable, rows readable.
"""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..models import Item

router = APIRouter()


@router.get("/api/items")
async def list_items(session: AsyncSession = Depends(get_session)) -> list[dict]:
    rows = (await session.execute(select(Item).order_by(Item.id))).scalars().all()
    return [
        {"id": r.id, "name": r.name, "description": r.description}
        for r in rows
    ]
