"""Regression cases for scripts/check_healthchecks.py: the template itself passes,
and each way a container can end up unwatched is caught.

    python3 scripts/tests/test_check_healthchecks.py
"""
import contextlib
import importlib.util
import io
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("check_healthchecks", REPO / "scripts" / "check_healthchecks.py")
hc = importlib.util.module_from_spec(spec)
# Registered before exec: its dataclasses look their module up by name.
sys.modules[spec.name] = hc
spec.loader.exec_module(hc)


def run(root: Path) -> tuple[int, str]:
    err = io.StringIO()
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err):
        code = hc.main(["check_healthchecks.py", str(root)])
    return code, err.getvalue()


class Project:
    """A throwaway repo with one compose file and an optional Dockerfile."""

    def __init__(self, compose: str, dockerfile: str | None = None):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "compose.deploy.yml").write_text(textwrap.dedent(compose))
        if dockerfile is not None:
            (self.root / "app").mkdir()
            (self.root / "app" / "Dockerfile").write_text(textwrap.dedent(dockerfile))

    def __enter__(self):
        return self.root

    def __exit__(self, *exc):
        self.tmp.cleanup()


class Template(unittest.TestCase):
    def test_the_template_passes(self):
        code, err = run(REPO)
        self.assertEqual(code, 0, err)


class Catches(unittest.TestCase):
    def test_image_only_service_without_healthcheck(self):
        with Project("""
            services:
              cache:
                image: redis:7
        """) as root:
            code, err = run(root)
            self.assertEqual(code, 1)
            self.assertIn("`cache`", err)

    def test_built_service_whose_dockerfile_has_none(self):
        with Project("""
            services:
              web:
                build:
                  context: ./app
        """, "FROM nginx:alpine\nCMD [\"nginx\"]\n") as root:
            self.assertEqual(run(root)[0], 1)

    def test_healthcheck_only_in_another_stage(self):
        with Project("""
            services:
              web:
                build:
                  context: ./app
                  target: prod
        """, """
            FROM node:22 AS dev
            HEALTHCHECK CMD true
            FROM nginx:alpine AS prod
        """) as root:
            self.assertEqual(run(root)[0], 1)

    def test_disabled_on_a_long_running_service(self):
        with Project("""
            services:
              api:
                image: example/api
                restart: unless-stopped
                healthcheck:
                  disable: true
        """) as root:
            code, err = run(root)
            self.assertEqual(code, 1)
            self.assertIn("disabled", err)

    def test_one_shot_must_say_so(self):
        with Project("""
            services:
              migrate:
                image: example/api
                restart: "no"
        """) as root:
            code, err = run(root)
            self.assertEqual(code, 1)
            self.assertIn("one-shot", err)


class Passes(unittest.TestCase):
    def test_other_worktrees_are_not_judged(self):
        with Project("""
            services:
              db:
                image: postgres:16-alpine
                healthcheck:
                  test: ["CMD-SHELL", "pg_isready"]
        """) as root:
            stray = root / ".claude" / "worktrees" / "other" / "compose.deploy.yml"
            stray.parent.mkdir(parents=True)
            stray.write_text("services:\n  cache:\n    image: redis:7\n")
            self.assertEqual(run(root)[0], 0)

    def test_compose_healthcheck(self):
        with Project("""
            services:
              db:
                image: postgres:16-alpine
                healthcheck:
                  test: ["CMD-SHELL", "pg_isready"]
        """) as root:
            self.assertEqual(run(root)[0], 0)

    def test_dockerfile_healthcheck_inherited_down_a_from_chain(self):
        with Project("""
            services:
              web:
                build:
                  context: ./app
                  target: final
        """, """
            FROM nginx:alpine AS base
            HEALTHCHECK CMD wget -q -O /dev/null http://127.0.0.1/healthz
            FROM base AS final
        """) as root:
            self.assertEqual(run(root)[0], 0)

    def test_one_shot_with_disable(self):
        with Project("""
            services:
              migrate:
                image: example/api
                restart: "no"
                healthcheck:
                  disable: true
        """) as root:
            self.assertEqual(run(root)[0], 0)

    def test_overlay_without_image_or_build_is_skipped(self):
        with Project("""
            services:
              backend:
                depends_on:
                  - db
        """) as root:
            self.assertEqual(run(root)[0], 0)


if __name__ == "__main__":
    unittest.main()
