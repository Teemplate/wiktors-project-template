"""Regression cases for fresh-clone context and instruction drift."""
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'check_agent_context.py'
spec = importlib.util.spec_from_file_location('agent_context_check', SCRIPT)
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)


class AgentContextTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        subprocess.run(['git', 'init', '-q', str(self.root)], check=True)
        self.manifest = {'version': 1, 'project': 'fixture', 'development_base': 'main', 'required_files': []}
        self.write('.agent-context.json', json.dumps(self.manifest))
        self.write('AGENTS.md', '# Fixture\n\nDevelopment base: `main`.\n')
        self.write('CLAUDE.md', (self.root / 'AGENTS.md').read_text())
        self.write('scripts/check_agent_context.py', '# fixture\n')
        self.write('.github/workflows/agent-context.yml', '# fixture\n')
        self.stage()

    def write(self, name, value):
        p = self.root / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(value)

    def stage(self):
        subprocess.run(['git', '-C', str(self.root), 'add', '.'], check=True)

    def pair(self, extra):
        content = '# Fixture\n\nDevelopment base: `main`.\n' + extra
        self.write('AGENTS.md', content)
        self.write('CLAUDE.md', content)

    def assert_error(self, fragment):
        self.assertTrue(any(fragment in e for e in checker.check(self.root)), checker.check(self.root))

    def test_valid_fresh_checkout(self):
        self.assertEqual([], checker.check(self.root))

    def test_missing_instructions(self):
        (self.root / 'AGENTS.md').unlink()
        self.assert_error('Required file is missing: AGENTS.md')

    def test_untracked_instructions_do_not_count(self):
        subprocess.run(['git', '-C', str(self.root), 'rm', '--cached', '-q', 'AGENTS.md'], check=True)
        self.assert_error('Required file is untracked: AGENTS.md')

    def test_drift(self):
        self.write('CLAUDE.md', '# Old policy\n')
        self.assert_error('AGENTS.md and CLAUDE.md differ')

    def test_size_limit(self):
        self.pair('x' * checker.MAX_BYTES)
        self.assert_error('exceeds')

    def test_missing_linked_reference(self):
        self.pair('[Runbook](./docs/missing.md)\n')
        self.assert_error('Required file is missing: docs/missing.md')

    def test_untracked_reference_fails_fresh_clone_contract(self):
        self.write('docs/private.md', 'Only present on this laptop')
        self.pair('[Required reference](./docs/private.md)\n')
        self.assert_error('Required file is untracked: docs/private.md')

    def test_optional_machine_notes_can_be_absent(self):
        self.manifest['optional_private_paths'] = ['local/infrastructure.md']
        self.write('.agent-context.json', json.dumps(self.manifest))
        self.pair('[Optional local notes](local/infrastructure.md)\n')
        self.assertEqual([], checker.check(self.root))

    def test_duplicate_hooks(self):
        self.write('.codex/config.toml', '[[hooks.SessionStart]]\nmatcher="startup"\n')
        self.write('.codex/hooks.json', json.dumps({'hooks': {'SessionStart': []}}))
        self.assert_error('Duplicate Codex hook sources')

    def test_claude_environment_variable_in_codex_hook(self):
        self.write('.codex/hooks.json', json.dumps({'hooks': {'SessionStart': [{'command': '$CLAUDE_PROJECT_DIR/hook.sh'}]}}))
        self.assert_error('not $CLAUDE_PROJECT_DIR')

    def test_wrong_case_reference_in_persona(self):
        self.write('.codex/agents/reviewer.toml', 'name="reviewer"\ndeveloper_instructions="Read .Codex/skills/safety.md"\n')
        self.stage()
        self.assert_error('invalid .Codex/ reference')

    def test_uninitialised_app(self):
        self.pair('\nLive at https://fixture.example.com\n')
        self.assert_error('unresolved scaffold text')

    def test_wrong_development_base(self):
        self.manifest['development_base'] = 'develop'
        self.write('.agent-context.json', json.dumps(self.manifest))
        self.assert_error('must state Development base: `develop`.')

    def test_parent_checkout_is_not_a_portable_reference(self):
        self.pair('[Guide](../other-project/AGENTS.md)\n')
        self.assert_error('required link leaves the repository')


if __name__ == '__main__':
    unittest.main()
