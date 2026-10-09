#!/usr/bin/env python3
"""Fail if any compose service could run without reporting its health.

Every container this template ships says whether it is healthy: the Pi's
status views and deploy/app-deploy's gate both read Docker's health status, and
a container without a healthcheck is the one nobody can watch -- it shows as
"running" right up to the moment it is serving errors. app-deploy refuses to
finish a deploy with such a container; this check catches it at merge time,
before anything is built.

A service passes when it
  * sets `healthcheck:` in its compose definition, or
  * builds a Dockerfile whose target stage has a HEALTHCHECK (directly or
    inherited from the stage it is built FROM), or
  * is a one-shot: `restart: "no"` with `healthcheck: disable: true` (migrate).

`healthcheck: disable: true` on anything long-running fails: switching the
check off is not the same as not needing one.

A definition with neither `image:` nor `build:` is an overlay (the
*.with-postgres.yml files add depends_on to a service defined elsewhere) and
is skipped; the file that defines the service is the one that must pass.

Standard library only, like the other scripts here: compose files in this repo
are written in one plain block style, and this reads that style line by line.

Usage: python3 scripts/check_healthchecks.py [repo root]   (exit 1 on failure)
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

COMPOSE_GLOBS = ("docker-compose.yml", "compose*.yml", "*/compose/*.yml", "**/compose*.yml")
SKIP_DIRS = {"node_modules", ".git", ".venv", "venv", "local"}


@dataclass
class Service:
    name: str
    file: Path
    lines: list[str] = field(default_factory=list)

    def has(self, key: str) -> bool:
        return any(re.match(rf"    {key}:", ln) for ln in self.lines)

    def value(self, key: str) -> str | None:
        for ln in self.lines:
            m = re.match(rf"    {key}:\s*(.*?)\s*$", ln)
            if m:
                return m.group(1).strip("\"'")
        return None

    def sub_value(self, parent: str, key: str) -> str | None:
        """`key` nested one level under `parent` (build: context:, healthcheck: disable:)."""
        inside = False
        for ln in self.lines:
            if re.match(rf"    {parent}:", ln):
                inside = True
                continue
            if inside:
                if not ln.startswith("      "):
                    if ln.strip():
                        inside = False
                    continue
                m = re.match(rf"      {key}:\s*(.*?)\s*$", ln)
                if m:
                    return m.group(1).strip("\"'")
        return None


def services_in(path: Path) -> list[Service]:
    found: list[Service] = []
    in_services = False
    current: Service | None = None
    for raw in path.read_text().splitlines():
        line = raw.split(" #")[0].rstrip() if not raw.lstrip().startswith("#") else ""
        if not line.strip():
            continue
        if not line.startswith(" "):
            in_services = line.startswith("services:")
            current = None
            continue
        if not in_services:
            continue
        m = re.match(r"  ([A-Za-z0-9_.-]+):\s*$", line)
        if m:
            current = Service(m.group(1), path)
            found.append(current)
        elif current is not None:
            current.lines.append(line)
    return found


def dockerfile_has_healthcheck(dockerfile: Path, target: str | None) -> bool:
    """HEALTHCHECK in the target stage (the last one when none is named), or in
    a stage it is built FROM -- Docker inherits it down a FROM chain."""
    stages: dict[str, tuple[str, bool]] = {}  # name -> (from, has_healthcheck)
    order: list[str] = []
    name = None
    for raw in dockerfile.read_text().splitlines():
        line = raw.strip()
        m = re.match(r"FROM\s+(\S+)(?:\s+AS\s+(\S+))?", line, re.IGNORECASE)
        if m:
            name = m.group(2) or f"#{len(order)}"
            stages[name] = (m.group(1), False)
            order.append(name)
        elif name and re.match(r"HEALTHCHECK\s+(?!NONE)", line, re.IGNORECASE):
            stages[name] = (stages[name][0], True)
        elif name and re.match(r"HEALTHCHECK\s+NONE", line, re.IGNORECASE):
            stages[name] = (stages[name][0], False)
    stage = target if target in stages else (order[-1] if order else None)
    seen: set[str] = set()
    while stage and stage in stages and stage not in seen:
        seen.add(stage)
        base, has = stages[stage]
        if has:
            return True
        stage = base
    return False


def compose_files(root: Path) -> list[Path]:
    files: set[Path] = set()
    for pattern in COMPOSE_GLOBS:
        for p in root.glob(pattern):
            if p.is_file() and not (set(p.relative_to(root).parts) & SKIP_DIRS):
                files.add(p)
    return sorted(files)


def problem(svc: Service, root: Path) -> str | None:
    if not (svc.has("image") or svc.has("build")):
        return None  # an overlay
    disabled = (svc.sub_value("healthcheck", "disable") or "").lower() == "true"
    one_shot = svc.value("restart") == "no"
    if disabled:
        return None if one_shot else "healthcheck is disabled on a long-running service"
    if svc.has("healthcheck"):
        return None
    if one_shot:
        return 'a one-shot (restart: "no") needs `healthcheck: disable: true` to say it has no health to report'
    if svc.has("build"):
        context = svc.sub_value("build", "context") or svc.value("build") or "."
        dockerfile = svc.sub_value("build", "dockerfile") or "Dockerfile"
        target = svc.sub_value("build", "target")
        # Compose resolves context against the compose file's project dir, which
        # for the fragments here is the repo root (they are `include`d from it).
        for base in (root, svc.file.parent):
            path = (base / context / dockerfile).resolve()
            if path.is_file():
                if dockerfile_has_healthcheck(path, target):
                    return None
                where = f"{path.relative_to(root.resolve())}" + (f" (stage {target})" if target else "")
                return f"no healthcheck: neither the compose service nor {where} defines one"
        return f"no healthcheck, and its Dockerfile ({context}/{dockerfile}) was not found to check"
    return "no healthcheck: an image-only service must define `healthcheck:` in compose"


def main(argv: list[str]) -> int:
    root = Path(argv[1] if len(argv) > 1 else ".").resolve()
    failures = []
    checked = 0
    for f in compose_files(root):
        for svc in services_in(f):
            checked += 1
            why = problem(svc, root)
            if why:
                failures.append(f"{f.relative_to(root)}: service `{svc.name}`: {why}")
    if failures:
        print("Services that would run without reporting their health:", file=sys.stderr)
        for line in failures:
            print(f"  {line}", file=sys.stderr)
        print("\nGive each one a healthcheck (compose `healthcheck:` or a Dockerfile HEALTHCHECK).", file=sys.stderr)
        return 1
    print(f"healthchecks ok: {checked} service definitions checked")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
