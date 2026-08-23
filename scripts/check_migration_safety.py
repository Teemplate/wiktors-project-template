#!/usr/bin/env python3
"""Fail when a new Alembic revision drops a table or column on the way *up*.

Only `upgrade()` matters: the deploy runs `alembic upgrade`, and nothing in the
deploy path ever calls `downgrade()`. A `downgrade()` that
drops the table its own `upgrade()` created is ordinary Alembic and destroys
nothing, but a plain grep over the file cannot tell the two apart -- which
made every table-creating revision fail this check.

Exit 0 if the revisions are safe (or the 'destructive-ok' label is set),
1 if a destructive operation reaches upgrade().
"""
from __future__ import annotations

import ast
import os
import re
import sys

DESTRUCTIVE = re.compile(r"drop_table|drop_column|DROP\s+TABLE|DROP\s+COLUMN", re.I)


def destructive_lines(source: str) -> list[str]:
    """Destructive lines reachable from upgrade().

    Anything we cannot parse or cannot locate an upgrade() in is reported in
    full: this guard fails closed, because a revision it cannot read is
    exactly the one worth a human's eyes.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return [line.strip() for line in source.splitlines() if DESTRUCTIVE.search(line)]

    upgrades = [
        n
        for n in tree.body
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == "upgrade"
    ]
    if not upgrades:
        return [line.strip() for line in source.splitlines() if DESTRUCTIVE.search(line)]

    hits: list[str] = []
    for node in upgrades:
        body = ast.get_source_segment(source, node) or ""
        hits += [line.strip() for line in body.splitlines() if DESTRUCTIVE.search(line)]
    return hits


def main(paths: list[str]) -> int:
    found: list[str] = []
    for path in paths:
        with open(path, encoding="utf-8") as fh:
            for line in destructive_lines(fh.read()):
                found.append(f"{path}: {line}")

    if not found:
        print("No destructive operations in upgrade().")
        return 0

    for line in found:
        print(line)

    if os.environ.get("ALLOWED") == "true":
        print("::warning::Destructive migration allowed by the 'destructive-ok' label.")
        return 0

    print(
        "::error::This migration drops a table or column in upgrade(). Data loss is "
        "not reversible by a rebuild. Add the 'destructive-ok' label to the PR if "
        "that is genuinely intended."
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
