"""Keep optional Claude provisioning separate from the default setup."""
from pathlib import Path
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
ROLE = ROOT / 'roles/claude'


class ClaudeBoundary(unittest.TestCase):
    def test_claude_tasks_are_only_reachable_through_the_opt_in_role(self):
        core = yaml.safe_load((ROOT / 'arch-core.yml').read_text())
        optional = [task for task in core[0]['tasks']
                    if task.get('ansible.builtin.include_role', {}).get('name') == 'claude']
        self.assertEqual(len(optional), 1)
        self.assertEqual(optional[0]['when'], 'claude_enabled | default(false) | bool')
        self.assertEqual(optional[0]['ansible.builtin.include_role']['apply'], {'tags': ['claude']})
        for name in ['arch-core.yml', 'arch-desktop.yml', 'arch-home.yml']:
            text = (ROOT / name).read_text()
            self.assertNotIn('claude-code', text)
            self.assertNotIn('.claude/', text)
            self.assertNotIn('ccodex', text)
        for name, parent in [('arch-desktop.yml', 'arch-core.yml'),
                             ('arch-home.yml', 'arch-desktop.yml')]:
            self.assertEqual(yaml.safe_load((ROOT / name).read_text())[0]['import_playbook'], parent)
        tasks = yaml.safe_load((ROLE / 'tasks/main.yml').read_text())
        self.assertTrue(any(task.get('community.general.pacman', {}).get('name') == 'claude-code'
                            for task in tasks))

    def test_claude_assets_do_not_leak_into_the_default_dotfile_tree(self):
        self.assertFalse(any(path.is_file() for path in (ROOT / 'user_home/.claude').rglob('*')))
        self.assertFalse((ROOT / 'user_home/.config/fish/completions/ccodex.fish').exists())
        for name in ['.claude/statusline.sh', '.claude/otel-headers.sh',
                     '.claude/hooks/git-guard.sh', '.config/fish/completions/ccodex.fish']:
            self.assertTrue((ROLE / 'files/user_home' / name).is_file(), name)
        for name in ['10-claude-personal.json.j2', '20-claude-telemetry.json.j2',
                     '30-claude-spend-meter.json.j2', '40-claude-lean-harness.json.j2']:
            self.assertTrue((ROLE / 'templates' / name).is_file(), name)
        self.assertFalse((ROOT / 'tests/test_ccodex.py').exists())

    def test_native_codex_keeps_the_shared_guard_and_working_agreements(self):
        self.assertTrue((ROOT / 'files/ssh-fish-guard.py').is_file())
        codex = (ROOT / 'roles/codex/tasks/main.yml').read_text()
        claude = (ROLE / 'tasks/main.yml').read_text()
        for text in [codex, claude]:
            self.assertIn('{{ playbook_dir }}/files/ssh-fish-guard.py', text)
        self.assertNotIn('roles/claude', codex)
        core = (ROOT / 'arch-core.yml').read_text()
        self.assertIn('.codex/AGENTS.md', core)
        self.assertIn('computerConfiguration: writing preferences', core)
        self.assertIn('computerConfiguration: diagnostics', core)
        self.assertIn('force: false', claude)  # Router credentials are never replaced.

    def test_claude_ci_stays_small_and_path_filtered(self):
        workflow = yaml.safe_load((ROOT.parents[1] / '.github/workflows/claude-mods.yml').read_text())
        triggers = workflow.get('on', workflow.get(True))  # PyYAML uses YAML 1.1 booleans.
        self.assertNotIn('schedule', triggers)
        for event in ['push', 'pull_request']:
            self.assertIn('linux/ansible/roles/claude/**', triggers[event]['paths'])
        self.assertEqual(len(workflow['jobs']), 1)
        job = next(iter(workflow['jobs'].values()))
        self.assertNotIn('strategy', job)
        commands = '\n'.join(step.get('run', '') for step in job['steps'])
        self.assertNotIn('npm install', commands)
        self.assertNotIn('claude plugin', commands)
        self.assertIn('node --check', commands)
        self.assertIn('unittest discover', commands)


if __name__ == '__main__':
    unittest.main()
