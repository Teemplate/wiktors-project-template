#!/usr/bin/env python3
"""check_preset.py — prove a block combination works, the way a user gets it.

    python3 scripts/check_preset.py site                 # one preset
    python3 scripts/check_preset.py --all                # every preset
    python3 scripts/check_preset.py api --unit --e2e     # plus its tests, plus its stack
    python3 scripts/check_preset.py --list

Copies this template (tracked and untracked-but-not-ignored files, so it checks
the working tree, not the last commit) into a scratch directory, runs the real
`init-project.sh <app> --blocks … --target … --no-remote --yes`, then checks the
project that comes out: the block manifest agrees with the files, the agent
context validates, and every generated compose file resolves. --unit installs
ONLY that project's requirements and runs its tests, so a module that imports a
pruned dependency fails here. --e2e runs its scripts/e2e.sh.

Template-only: init-project.sh deletes this file from new projects.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# name -> (blocks, target). "classic" is init-project.sh's default.
PRESETS = {
    "full": ("web,api,worker,postgres", "pi-compose"),
    "classic": ("web,api,postgres", "pi-compose"),
    "site": ("web", "pages"),
    "web-api": ("web,api", "pi-compose"),
    "api": ("api,postgres", "pi-compose"),
    "worker": ("worker,postgres", "pi-compose"),
    "bot": ("worker", "pi-compose"),
}


def run(cmd: list[str], cwd: Path, env: dict | None = None) -> None:
    print(f"    $ {' '.join(cmd)}", flush=True)
    subprocess.run(cmd, cwd=cwd, check=True, env={**os.environ, **(env or {})})


def files(root: Path) -> list[str]:
    out = subprocess.run(
        ["git", "-C", str(root), "ls-files", "--cached", "--others", "--exclude-standard"],
        capture_output=True, text=True, check=True,
    )
    return [f for f in out.stdout.splitlines() if (root / f).exists()]


def copy_template(dest: Path) -> None:
    for rel in files(ROOT):
        src, dst = ROOT / rel, dest / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst, follow_symlinks=False)


def check(name: str, unit: bool, e2e: bool, docker_python: bool, keep: bool) -> None:
    blocks, target = PRESETS[name]
    print(f"== {name}: {blocks} on {target}", flush=True)
    tmp = Path(tempfile.mkdtemp(prefix=f"preset-{name}-"))
    app = f"preset-{name}"
    project = tmp / app
    try:
        copy_template(project)
        run(["./scripts/init-project.sh", app, "--blocks", blocks, "--target", target,
             "--no-remote", "--yes"], project)

        run([sys.executable, "scripts/blocks.py", "check"], project)
        run([sys.executable, "scripts/check_agent_context.py"], project)
        assert not (project / "scripts/check_preset.py").exists(), "init left the template-only preset check"

        env = {"E2E_PROJECT": "ci", "COMPOSE_PROJECT_NAME": app}
        (project / ".env.e2e").write_text("E2E_PROJECT=ci\n")
        for f, extra in [("docker-compose.yml", []), ("compose.deploy.yml", []),
                         ("compose.e2e.yml", ["--env-file", ".env.e2e"])]:
            if (project / f).exists():
                run(["docker", "compose", "-f", f, *extra, "config", "--quiet"], project, env)
        (project / ".env.e2e").unlink()
        has_deploy = (project / "compose.deploy.yml").exists()
        assert has_deploy == (target == "pi-compose"), "compose.deploy.yml does not match the target"

        if unit:
            unit_checks(project, docker_python)
        if e2e:
            run(["./scripts/e2e.sh"], project)
        print(f"== {name}: ok\n", flush=True)
    finally:
        if keep:
            print(f"   kept: {project}")
        else:
            shutil.rmtree(tmp, ignore_errors=True)


def unit_checks(project: Path, docker_python: bool) -> None:
    backend, frontend = project / "backend", project / "frontend"
    if backend.exists():
        script = ("python -m venv /tmp/v && /tmp/v/bin/pip install -q --disable-pip-version-check "
                  "-r requirements-dev.txt && PYTHONDONTWRITEBYTECODE=1 /tmp/v/bin/pytest -p no:cacheprovider")
        if docker_python:
            # The same Python as backend/Dockerfile and CI, whatever the host has.
            run(["docker", "run", "--rm", "-u", f"{os.getuid()}:{os.getgid()}", "-e", "HOME=/tmp",
                 "-v", f"{backend}:/src:z", "-w", "/src", "python:3.12-slim", "sh", "-c", script], project)
        else:
            run(["sh", "-c", script.replace("/tmp/v", str(project / ".venv-preset"))], backend)
    if frontend.exists():
        local = ROOT / "frontend" / "node_modules"
        if local.exists():
            # Same package.json apart from its name: reuse the install.
            (frontend / "node_modules").symlink_to(local)
        else:
            run(["npm", "ci", "--no-audit", "--no-fund"], frontend)
        for script in ("typecheck", "test", "build"):
            run(["npm", "run", script], frontend)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("presets", nargs="*")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--unit", action="store_true", help="install and run each project's own tests")
    parser.add_argument("--e2e", action="store_true", help="run each project's scripts/e2e.sh")
    parser.add_argument("--docker-python", action="store_true", help="run backend tests in python:3.12-slim")
    parser.add_argument("--keep", action="store_true", help="leave the generated projects on disk")
    args = parser.parse_args()
    if args.list:
        for name, (blocks, target) in PRESETS.items():
            print(f"{name:<8} {blocks} on {target}")
        return 0
    names = list(PRESETS) if args.all else args.presets
    unknown = [n for n in names if n not in PRESETS]
    if not names or unknown:
        parser.error(f"choose presets from: {', '.join(PRESETS)}")
    for name in names:
        check(name, args.unit, args.e2e, args.docker_python, args.keep)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
