"""Invariants of the seed data itself.

Deliberately database-free, like the rest of this suite: a fresh clone with no
Postgres and no .env must still be able to run `pytest`. The real database path
is covered where it belongs — CI migrates a live Postgres up and back down, and
`scripts/e2e.sh` runs the seed against a disposable stack and refuses to start
the browser tests if it produced no rows.
"""

from app.seed import SEED_ITEMS


def test_enough_rows_to_make_assertions_meaningful():
    # One row cannot distinguish "the list renders" from "the list renders the
    # wrong thing", and the e2e suite asserts on this count.
    assert len(SEED_ITEMS) >= 3


def test_names_are_unique():
    # The seed is idempotent by looking rows up by name; duplicates would make
    # a re-run silently insert nothing for the shadowed entry.
    names = [item["name"] for item in SEED_ITEMS]
    assert len(names) == len(set(names))


def test_every_item_is_complete():
    for item in SEED_ITEMS:
        assert item["name"].strip()
        assert item["description"].strip()
