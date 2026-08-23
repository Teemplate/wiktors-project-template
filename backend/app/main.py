"""Minimal FastAPI app.

The health endpoint exists for the DEPLOY GATE, not for humans: the deploy
agent polls it and fails (and rolls back) if the container never answers. A
container that starts and then dies on a bad import would otherwise be reported
as a successful deploy.

**`/api/health` deliberately does not touch the database.** It answers `ok`
while every data route is broken, which is exactly why the deploy gate checks a
real data route (`/api/items`) as well. Checking only health is how a deploy
goes green with a dead database behind it.
"""

from fastapi import Depends, FastAPI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .config import settings
from .db import get_session
from .models import Item

app = FastAPI(title=settings.app_name)


@app.get("/api/health")
async def health() -> dict:
    """Liveness + a signal that config actually loaded.

    `ok` is what the deploy gate checks. Report the placeholder secret rather
    than hiding it — shipping the dev default to production is a real incident,
    and this is the cheapest place to notice.
    """
    return {
        "ok": True,
        "app": settings.app_name,
        "placeholder_secret": settings.is_placeholder_secret,
    }


@app.get("/api/hello")
async def hello() -> dict:
    return {"message": f"hello from {settings.app_name}"}


@app.get("/api/items")
async def list_items(session: AsyncSession = Depends(get_session)) -> list[dict]:
    """The example data route.

    This is what the deploy gate and the e2e suite check, because it is the
    cheapest thing that proves the whole path works: config loaded, engine
    built, migration applied, database reachable, rows readable.
    """
    rows = (await session.execute(select(Item).order_by(Item.id))).scalars().all()
    return [
        {"id": r.id, "name": r.name, "description": r.description}
        for r in rows
    ]
