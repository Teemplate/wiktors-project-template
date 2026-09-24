"""Minimal FastAPI app — the `api` block.

The health endpoint exists for the DEPLOY GATE, not for humans: the deploy
agent polls it and fails (and rolls back) if the container never answers. A
container that starts and then dies on a bad import would otherwise be reported
as a successful deploy.

**`/api/health` deliberately does not touch the database.** It answers `ok`
while every data route is broken, which is exactly why the deploy gate checks a
real data route as well (`/api/items` when the `postgres` block is present).
Checking only health is how a deploy goes green with a dead database behind it.

Routes live in `app/routes/`, one module per concern, each exposing a `router`.
They are discovered rather than imported by name, so a route that only makes
sense with another block (`items.py` needs `postgres`) is removed by deleting
its file — see docs/BLOCKS.md.
"""

import importlib
import pkgutil

from fastapi import FastAPI

from . import routes
from .config import settings

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


# Sorted, so route registration order never depends on the filesystem.
for module in sorted(pkgutil.iter_modules(routes.__path__), key=lambda m: m.name):
    app.include_router(importlib.import_module(f"{routes.__name__}.{module.name}").router)
