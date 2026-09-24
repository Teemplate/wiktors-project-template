"""Regression cases for scripts/blocks.py: ownership rules, marked sections, and
a remove-then-add round trip that must restore exactly what the template has.

    python3 scripts/tests/test_blocks.py
"""
import contextlib
import importlib.util
import io
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("blocks", REPO / "scripts" / "blocks.py")
blocks = importlib.util.module_from_spec(spec)
spec.loader.exec_module(blocks)

MANIFEST = json.loads((REPO / "blocks.json").read_text())
KNOWN = blocks.names(MANIFEST)


def quiet(fn, *args):
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        return fn(*args)


class Rules(unittest.TestCase):
    def kept(self, rel, *on):
        return blocks.kept(MANIFEST, rel, set(on))

    def test_a_file_needs_every_rule_that_matches_it(self):
        items = "frontend/src/features/items/index.tsx"
        self.assertTrue(self.kept(items, "web", "api", "postgres", "pi-compose"))
        self.assertFalse(self.kept(items, "web", "api", "pi-compose"))
        self.assertFalse(self.kept(items, "api", "postgres", "pi-compose"))

    def test_any_of_rules(self):
        self.assertTrue(self.kept("backend/app/config.py", "worker", "pi-compose"))
        self.assertFalse(self.kept("backend/app/config.py", "web", "pages"))

    def test_glue_globs(self):
        glue = "backend/compose/api.deploy.with-postgres.yml"
        self.assertTrue(self.kept(glue, "api", "postgres", "pi-compose"))
        self.assertFalse(self.kept(glue, "api", "pi-compose"))
        self.assertTrue(self.kept("backend/compose/api.deploy.yml", "api", "pi-compose"))

    def test_targets_own_files_too(self):
        self.assertFalse(self.kept("deploy/app-deploy", "web", "pages"))
        self.assertTrue(self.kept(".github/workflows/pages.yml", "web", "pages"))

    def test_unowned_files_belong_to_everyone(self):
        self.assertTrue(self.kept("docs/DEVELOPING.md", "worker", "pi-compose"))

    def test_every_rule_names_real_blocks(self):
        for rule in MANIFEST["files"]:
            for name in blocks.when_names(rule["when"]):
                self.assertIn(name, KNOWN, rule["when"])


class Validation(unittest.TestCase):
    def test_postgres_needs_something_to_migrate_it(self):
        with self.assertRaises(blocks.BlockError):
            blocks.validate(MANIFEST, ["web", "postgres"], "pi-compose")

    def test_pages_hosts_only_web(self):
        with self.assertRaises(blocks.BlockError):
            blocks.validate(MANIFEST, ["web", "api"], "pages")
        blocks.validate(MANIFEST, ["web"], "pages")

    def test_unknown_names_are_refused(self):
        with self.assertRaises(blocks.BlockError):
            blocks.validate(MANIFEST, ["website"], "pi-compose")
        with self.assertRaises(blocks.BlockError):
            blocks.validate(MANIFEST, ["web"], "heroku")


class Marked(unittest.TestCase):
    TEXT = "a\n# block:api\nb\n# /block\n<!-- block:web+api -->\nc\n<!-- /block -->\n# block:api|worker\nd\n# /block\ne\n"

    def strip(self, *on):
        return blocks.strip_marked(self.TEXT, set(on), KNOWN)

    def test_kept_sections_keep_their_markers(self):
        self.assertEqual(self.strip("web", "api", "worker"), self.TEXT)

    def test_unsatisfied_sections_go_whole(self):
        self.assertEqual(self.strip("worker"), "a\n# block:api|worker\nd\n# /block\ne\n")
        self.assertEqual(self.strip("web"), "a\ne\n")

    def test_malformed_sections_are_errors(self):
        for bad in ["# block:api\nx\n", "x\n# /block\n", "# block:api\n# block:web\n# /block\n",
                    "# block:nosuch\n# /block\n"]:
            with self.assertRaises(blocks.BlockError):
                blocks.strip_marked(bad, {"api"}, KNOWN)


class RoundTrip(unittest.TestCase):
    """Cut a project down, add a block back from the template, and compare."""

    # init-project.sh's skip_files: never rewritten, in a project or here.
    SKIP = {"SETUP.md", "init-project.sh", "check_agent_context.py", "test_agent_context.py", "blocks.py"}

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.template = self.tmp / "template"
        self.project = self.tmp / "project"
        for root in (self.template, self.project):
            for rel in self.files():
                (root / rel).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(REPO / rel, root / rel)
        ctx = json.loads((self.project / ".agent-context.json").read_text())
        ctx.update(project="demo", is_template=False)
        (self.project / ".agent-context.json").write_text(json.dumps(ctx))
        # What init-project.sh does to a copy: rewrite the placeholders.
        self.subs = blocks.substitutions(self.project)
        for rel in self.files():
            path = self.project / rel
            if path.name in self.SKIP:
                continue
            path.write_text(self.rewrite(path.read_text(errors="replace")))

    def rewrite(self, text):
        for old, new in self.subs:
            text = text.replace(old, new)
        return text

    @staticmethod
    def files():
        out = subprocess.run(["git", "-C", str(REPO), "ls-files", "--cached", "--others", "--exclude-standard"],
                             capture_output=True, text=True, check=True).stdout.split()
        return [f for f in out if (REPO / f).is_file()]

    def run_blocks(self, *argv):
        code = quiet(blocks.main, ["--root", str(self.project), *argv])
        self.assertEqual(code, 0, argv)

    def snapshot(self, root, on):
        known = blocks.names(MANIFEST)
        snap = {}
        for rel in self.files():
            if not (root / rel).exists() or not blocks.kept(MANIFEST, rel, on):
                continue
            text = (root / rel).read_text(errors="replace")
            if root == self.template and Path(rel).name not in self.SKIP:
                text = self.rewrite(text)
            if rel in MANIFEST["marked"]:
                text = blocks.strip_marked(text, on, known, rel)
            snap[rel] = text
        return snap

    def test_set_then_add_restores_the_template(self):
        self.run_blocks("set", "--blocks", "api", "--target", "pi-compose")
        self.assertFalse((self.project / "frontend").exists())
        self.assertFalse((self.project / "backend/migrations").exists())
        self.assertNotIn("sqlalchemy", (self.project / "backend/requirements.txt").read_text())
        self.run_blocks("check")

        self.run_blocks("add", "web", "postgres", "--from", str(self.template))
        self.run_blocks("check")
        on = {"web", "api", "postgres", "pi-compose"}
        want = self.snapshot(self.template, on)
        have = self.snapshot(self.project, on)
        # The generated files and the manifest differ by design (the selection);
        # everything else must match the template byte for byte.
        for rel in ["blocks.json", "docker-compose.yml", "compose.deploy.yml", "compose.e2e.yml",
                    "deploy/app-deploy", ".agent-context.json"]:
            want.pop(rel, None)
            have.pop(rel, None)
        self.assertEqual(sorted(have), sorted(want))
        for rel in want:
            self.assertEqual(have[rel], want[rel], rel)

    def test_set_refuses_to_add(self):
        self.run_blocks("set", "--blocks", "web", "--target", "pages")
        code = quiet(blocks.main, ["--root", str(self.project), "set", "--blocks", "web,api"])
        self.assertEqual(code, 2)

    def test_the_deploy_agent_learns_the_blocks(self):
        self.run_blocks("set", "--blocks", "worker", "--target", "pi-compose")
        agent = (self.project / "deploy/app-deploy").read_text()
        self.assertIn('BLOCKS="worker"', agent)
        self.assertIn('DATA_ROUTE=""', agent)

    def test_a_pages_project_has_no_deploy_stack(self):
        self.run_blocks("set", "--blocks", "web", "--target", "pages")
        self.assertFalse((self.project / "compose.deploy.yml").exists())
        self.assertFalse((self.project / "deploy").exists())
        self.assertTrue((self.project / ".github/workflows/pages.yml").exists())
        self.assertFalse((self.project / "frontend/nginx/snippets/api-proxy.conf.template").exists())


if __name__ == "__main__":
    unittest.main()
