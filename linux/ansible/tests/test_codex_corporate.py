"""Verify opt-in boundaries, reviewed corporate reads and private hook merging."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
ROLE = ROOT / 'roles/codex_corporate'


def load(name):
    spec = importlib.util.spec_from_file_location(name.replace('-', '_'), ROLE / 'files' / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Corporate(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)

    def test_role_is_opt_in_and_keeps_exact_reviewed_reads(self):
        core = yaml.safe_load((ROOT / 'arch-core.yml').read_text())
        optional = next(task for task in core[0]['tasks']
                        if task.get('ansible.builtin.include_role', {}).get('name') == 'codex_corporate')
        self.assertEqual(optional['when'], 'codex_corporate_enabled | default(false) | bool')
        self.assertEqual(optional['ansible.builtin.include_role']['apply'],
                         {'become': True, 'tags': ['codex_corporate']})
        for name in ['arch-desktop.yml', 'arch-home.yml']:
            self.assertNotIn('codex_corporate', (ROOT / name).read_text())
        policy = yaml.safe_load((ROLE / 'defaults/main.yml').read_text())['codex_corporate_mcp_policy']
        self.assertEqual(set(policy), {'mcp_servers'})
        expected = {
            'confluence': {'confluence_advanced_search', 'confluence_convert_to_markdown',
                          'confluence_cql_search', 'confluence_get_footer_comments',
                          'confluence_get_inline_comments', 'confluence_get_page',
                          'confluence_get_page_source', 'confluence_get_page_versions',
                          'confluence_list_spaces', 'confluence_search_pages'},
            'vkworkspace-assistant': {'messenger-list-chats', 'messenger-list-messages',
                'messenger-resolve-message-url', 'messenger-search', 'messenger-search-summaries',
                'orgstructure-get-root', 'orgstructure-search', 'orgstructure-unit-get',
                'orgstructure-unit-staff-get', 'orgstructure-unit-subunits-get', 'orgstructure-users-get'},
            'docs-vk-team': {'list-repos', 'search-docs'},
        }
        self.assertEqual(set(policy['mcp_servers']), set(expected))
        for name, server in policy['mcp_servers'].items():
            self.assertEqual(set(server['enabled_tools']), expected[name])
            self.assertEqual(server['default_tools_approval_mode'], 'prompt')
            self.assertEqual(server['tools'], {tool: {'approval_mode': 'auto'} for tool in expected[name]})
            self.assertFalse(set(server['disabled_tools']) & expected[name])

    def test_hook_merge_check_mode_idempotence_and_symlink(self):
        module = load('configure-hooks')
        path = self.home / 'hooks.json'
        config = {'custom': 'preserve', 'hooks': {'PreToolUse': [
            {'matcher': 'Read', 'hooks': [{'type': 'command', 'command': 'personal-handler'}]}]}}
        path.write_text(json.dumps(config))
        original = path.read_text()
        self.assertTrue(module.configure(path, self.home, check=True))
        self.assertEqual(path.read_text(), original)
        self.assertTrue(module.configure(path, self.home))
        actual = json.loads(path.read_text())
        self.assertEqual(actual['custom'], 'preserve')
        self.assertEqual(actual['hooks']['PreToolUse'][0], config['hooks']['PreToolUse'][0])
        self.assertFalse(module.configure(path, self.home))
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        link = self.home / 'link'
        link.symlink_to(path)
        with self.assertRaises(ValueError):
            module.configure(link, self.home)

    def test_oauth_cache_is_read_only_and_optional(self):
        module = load('workspace-headers')
        self.assertEqual(module.headers(self.home), {})
        (self.home / '.claude').mkdir()
        (self.home / '.claude.json').write_text(json.dumps({'mcpServers': {
            'vkworkspace-assistant': {'url': 'https://assistant.example/mcp/'}}}))
        path = self.home / '.claude/.credentials.json'
        cache = {'mcpOAuth': {'entry': {'serverName': 'vkworkspace-assistant',
            'serverUrl': 'https://assistant.example/mcp/', 'accessToken': 'synthetic-token',
            'refreshToken': 'never-read-or-copy', 'expiresAt': (time.time() + 1000) * 1000}}}
        path.write_text(json.dumps(cache))
        original = path.read_bytes()
        self.assertEqual(module.headers(self.home), {'Authorization': 'Bearer synthetic-token'})
        self.assertEqual(path.read_bytes(), original)
        cache['mcpOAuth']['entry']['expiresAt'] = 0
        path.write_text(json.dumps(cache))
        self.assertEqual(module.headers(self.home), {})

    def test_session_context_only_matches_corporate_origin(self):
        module = load('work-context')
        for url in ['https://gitlab.corp.mail.ru/a/b', 'git@gitlab.corp.mail.ru:a/b']:
            self.assertTrue(module.corporate(url))
        for url in ['https://github.com/a/b', 'https://gitlab.corp.mail.ru.evil/a',
                    'https://gitlab.corp.mail.ru@evil/a']:
            self.assertFalse(module.corporate(url))
        result = subprocess.run([sys.executable, str(ROLE / 'files/work-context.py')],
                                input=json.dumps({'cwd': str(self.home)}), capture_output=True,
                                text=True, timeout=5, check=True)
        self.assertEqual(result.stdout, '')


if __name__ == '__main__':
    unittest.main()
