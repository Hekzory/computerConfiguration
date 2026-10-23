"""Policy edits must preserve desktop state, credentials, comments and trust."""
import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import tomllib
import unittest

ROOT = Path(__file__).resolve().parents[1]
FILES = ROOT / 'roles/codex/files'
sys.path.insert(0, str(FILES))
SPEC = importlib.util.spec_from_file_location('codex_config_edit', FILES / 'config_edit.py')
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class UserPolicy(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'config.toml'
        self.original = '''# User comments remain
model = "gpt-6.1-sol"
web_search = "live"
model_reasoning_summary = "detailed"
[features]
analytics_plan_history = true # deprecated
memories = true
[desktop]
preventSleepWhileRunning = true
[desktop.appearanceDarkChromeTheme]
surface = "#282a36"
[hooks.state."private:user-hook"]
trusted_hash = "opaque"
[otel.metrics_exporter.otlp-http.headers]
Authorization = "Bearer synthetic-secret"
[plugins."browser@openai-bundled"]
enabled = true
'''
        self.path.write_text(self.original)
        self.path.chmod(0o600)

    def test_narrow_updates_removals_check_mode_and_idempotence(self):
        updates = {'desktop': {'ambient-suggestions-enabled': False}}
        removals = [['features', 'analytics_plan_history']]
        self.assertTrue(MODULE.configure(self.path, updates, removals, check=True))
        self.assertEqual(self.path.read_text(), self.original)
        self.assertTrue(MODULE.configure(self.path, updates, removals))
        expected = tomllib.loads(self.original)
        del expected['features']['analytics_plan_history']
        expected['desktop']['ambient-suggestions-enabled'] = False
        self.assertEqual(tomllib.loads(self.path.read_text()), expected)
        self.assertIn('# User comments remain', self.path.read_text())
        self.assertFalse(MODULE.configure(self.path, updates, removals))

    def test_dotted_keys_inline_tables_and_multiline_strings(self):
        self.path.write_text('''"desktop"."ambient-suggestions-enabled" = true
"desktop"."custom" = """Text
[looks.like.a.table]
"""
features = { analytics_plan_history = true, memories = true }
''')
        MODULE.configure(self.path, {'desktop': {'ambient-suggestions-enabled': False}},
                         [['features', 'analytics_plan_history']])
        config = tomllib.loads(self.path.read_text())
        self.assertEqual(config['features'], {'memories': True})
        self.assertFalse(config['desktop']['ambient-suggestions-enabled'])
        self.assertIn('[looks.like.a.table]', config['desktop']['custom'])

    def test_named_skill_disables_preserve_other_rules_and_win_over_paths(self):
        self.path.write_text(self.original + '''
[[skills.config]]
name = "work-pets:pets"
enabled = true
[[skills.config]]
# Preserve this unrelated rule and its comment.
path = "/custom/skill/SKILL.md"
enabled = false
[[skills.config]]
path = "/plugins/work-pets/pets/SKILL.md"
enabled = true
''')
        original = self.path.read_text()
        names = ['work-pets:create-pet', 'work-pets:pets', 'work-pets:update-pet']
        before = tomllib.loads(original)
        self.assertTrue(MODULE.configure(self.path, {}, check=True, disabled_skills=names))
        self.assertEqual(self.path.read_text(), original)
        self.assertTrue(MODULE.configure(self.path, {}, disabled_skills=names))
        after = tomllib.loads(self.path.read_text())
        rules = after.pop('skills')['config']
        self.assertEqual(rules[:2], before.pop('skills')['config'][1:])
        self.assertEqual(rules[2:], [{'name': name, 'enabled': False} for name in names])
        self.assertEqual(after, before)
        self.assertIn('# Preserve this unrelated rule and its comment.', self.path.read_text())
        self.assertFalse(MODULE.configure(self.path, {}, disabled_skills=names))

    def test_invalid_skill_rules_are_not_overwritten(self):
        for rules in ('"foreign string"', '["foreign string"]'):
            original = self.original + '\n[skills]\nconfig = ' + rules + '\n'
            self.path.write_text(original)
            with self.assertRaises(ValueError):
                MODULE.configure(self.path, {}, disabled_skills=['work-pets:pets'])
            self.assertEqual(self.path.read_text(), original)

    def test_invalid_or_conflicting_config_is_unchanged(self):
        for original in ('[broken', 'desktop = "foreign string"\n'):
            self.path.write_text(original)
            with self.assertRaises(ValueError):
                MODULE.configure(self.path, {'desktop': {'ambient-suggestions-enabled': False}})
            self.assertEqual(self.path.read_text(), original)

    def test_rejects_symlink_and_stale_snapshot(self):
        with self.assertRaises(ValueError):
            MODULE.write_config(self.path, 'stale', 'model = "other"\n')
        link = self.path.parent / 'link'
        link.symlink_to(self.path)
        with self.assertRaises(ValueError):
            MODULE.configure(link, {'model': 'other'})
        self.assertEqual(self.path.read_text(), self.original)

    def test_cli_diagnostics_do_not_disclose_private_values(self):
        self.path.write_text('token = "synthetic-secret\n')
        result = subprocess.run([sys.executable, str(FILES / 'configure-user.py'),
                                 '--config', str(self.path)], capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 1)
        self.assertNotIn('synthetic-secret', result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
