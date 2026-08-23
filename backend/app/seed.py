"""Populate an empty database with enough data to actually use the app.

    python -m app.seed            # idempotent: safe to run repeatedly
    python -m app.seed --reset    # delete seeded rows first

**Why a template ships this at all.** An empty database is not a runnable app.
Without a seed, every developer and every agent session hand-builds throwaway
rows, differently each time, and no UI test can assert anything: against an
empty list view, every assertion passes vacuously. It is also the difference
between "clone, up, and click around" and half an hour of setup.

A seed script and a working end-to-end suite go together, and that is not a
coincidence -- `scripts/e2e.sh` calls this file, and refuses to run the browser
tests if it did not produce data.

Rules for extending it:
  - **Idempotent.** Re-running must not duplicate or fail. Look the row up
    before inserting it.
  - **Deterministic.** No random values and no `datetime.now()` in the data
    itself, or tests asserting on it will flake.
  - **Never destructive by default.** `--reset` must be asked for explicitly,
    and must only ever delete rows this file created.
  - **Never any real credential or personal data.** This runs in CI.
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from sqlalchemy import delete, func, select

from .db import SessionLocal
from .models import Item

# The e2e suite asserts on this count, so keep it >= 3: one row cannot
# distinguish "the list renders" from "the list renders the wrong thing".
SEED_ITEMS: list[dict[str, str]] = [
    {"name": "First item", "description": "Seeded so the list view has something to show."},
    {"name": "Second item", "description": "Two rows prove ordering and repetition."},
    {"name": "Third item", "description": "Three rows make an empty-vs-populated test meaningful."},
]


async def seed(reset: bool = False) -> int:
    """Insert the seed rows. Returns the number of rows in the table afterwards."""
    async with SessionLocal() as session:
        if reset:
            await session.execute(
                delete(Item).where(Item.name.in_([i["name"] for i in SEED_ITEMS]))
            )
            await session.commit()

        for spec in SEED_ITEMS:
            existing = await session.scalar(select(Item).where(Item.name == spec["name"]))
            if existing is None:
                session.add(Item(**spec))
        await session.commit()

        return await session.scalar(select(func.count()).select_from(Item)) or 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--reset",
        action="store_true",
        help="delete the rows this script creates before re-inserting them",
    )
    args = parser.parse_args()

    count = asyncio.run(seed(reset=args.reset))
    print(f"seeded; items table now holds {count} row(s)")
    # Fail loudly rather than letting a caller believe an empty database is seeded.
    if count < len(SEED_ITEMS):
        print(
            f"::error::expected at least {len(SEED_ITEMS)} items, found {count}",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
