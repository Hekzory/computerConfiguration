import contextlib
import http.client
import importlib.machinery
import importlib.util
import io
import json
import os
import subprocess
import sys
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch


ROOT = Path(__file__).resolve().parents[1]
LOADER = importlib.machinery.SourceFileLoader('ccodex', str(ROOT / 'usr/local/bin/ccodex'))
SPEC = importlib.util.spec_from_loader(LOADER.name, LOADER)
ccodex = importlib.util.module_from_spec(SPEC)
LOADER.exec_module(ccodex)


class CcodexTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.env = patch.dict(os.environ, {'HOME': str(self.home)}, clear=True)
        self.env.start()
        self.addCleanup(self.env.stop)
        self.directory = self.home / '.claude-code-router'
        self.directory.mkdir()
        self.config_path = self.directory / 'config.json'
        self.config = json.loads((ROOT / 'files/ccodex-router.json').read_text())
        self.config_path.write_text(json.dumps(self.config))
        self.auth = self.directory / 'codex_auth.json'
        self.ccr = self.home / '.local/share/ccodex/router/node_modules/.bin/ccr'
        self.ccr.parent.mkdir(parents=True)
        self.ccr.touch()

    def mock_router(self):
        router = MagicMock()
        router.directory = self.directory
        router.port = 1455
        router.config = self.config
        router.request.return_value = (200, {'id': 'codex,gpt-6.1-sol', 'context_window': 750000})
        return router

    def test_seed_uses_loopback_and_subscription_transformers(self):
        self.assertEqual(self.config['HOST'], '127.0.0.1')
        self.assertEqual(self.config['PORT'], 1455)
        self.assertFalse(self.config['LOG'])
        provider, = self.config['Providers']
        self.assertEqual(provider['api_base_url'], 'https://chatgpt.com/backend-api/codex')
        self.assertEqual(provider['models_api_url'], 'https://chatgpt.com/backend-api/codex/models')
        self.assertEqual(provider['models'], ['gpt-6.1-sol', 'gpt-6-astra', 'gpt-6-luna'])
        self.assertEqual(provider['api_key'], 'oauth-placeholder')
        self.assertEqual(provider['transformer']['use'], ['openai-responses', 'codex'])
        for model in self.config['Router'].values():
            self.assertIn(model.removeprefix('codex,'), provider['models'])

    def run_models_api_migration(self):
        return subprocess.run([sys.executable, str(ROOT / 'files/ensure_ccodex_models_api.py'),
                               str(self.config_path)], capture_output=True, text=True)

    def test_models_api_migration_keeps_credentials_models_and_permissions(self):
        codex = {'name': 'codex', 'api_key': 'oauth-placeholder', 'models': ['custom-model']}
        existing = {'Providers': [{'name': 'other', 'api_key': 'private-secret'}, codex],
                    'Router': {'default': 'other,local-model'}}
        self.config_path.write_text(json.dumps(existing))
        self.config_path.chmod(0o600)
        first = self.run_models_api_migration()
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(first.stdout.strip(), 'updated')
        updated = json.loads(self.config_path.read_text())
        self.assertEqual(updated['Providers'][1]['models_api_url'],
                         'https://chatgpt.com/backend-api/codex/models')
        self.assertEqual(updated['Providers'][0], existing['Providers'][0])
        self.assertEqual(updated['Providers'][1]['models'],
                         ['custom-model', 'gpt-6.1-sol', 'gpt-6-astra', 'gpt-6-luna'])
        self.assertEqual(codex['models'], ['custom-model'])
        self.assertEqual(updated['Router'], existing['Router'])
        self.assertEqual(self.config_path.stat().st_mode & 0o777, 0o600)
        after_first = self.config_path.read_bytes()
        second = self.run_models_api_migration()
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual(second.stdout.strip(), 'unchanged')
        self.assertEqual(self.config_path.read_bytes(), after_first)

    def test_models_api_migration_respects_existing_custom_url(self):
        self.config['Providers'][0]['models_api_url'] = 'https://custom.example/models'
        original = json.dumps(self.config)
        self.config_path.write_text(original)
        result = self.run_models_api_migration()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), 'unchanged')
        self.assertEqual(self.config_path.read_text(), original)

    def test_models_api_migration_adds_missing_tiers_without_replacing_custom_url(self):
        self.config['Providers'][0]['models_api_url'] = 'https://custom.example/models'
        self.config['Providers'][0]['models'] = ['custom-model', 'gpt-6-astra']
        self.config_path.write_text(json.dumps(self.config))
        result = self.run_models_api_migration()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), 'updated')
        updated = json.loads(self.config_path.read_text())
        provider = updated['Providers'][0]
        self.assertEqual(provider['models_api_url'], 'https://custom.example/models')
        self.assertEqual(provider['models'],
                         ['custom-model', 'gpt-6-astra', 'gpt-6.1-sol', 'gpt-6-luna'])

    def test_models_api_migration_rejects_invalid_models_without_overwriting(self):
        self.config['Providers'][0]['models'] = 'not-a-model-list'
        original = json.dumps(self.config)
        self.config_path.write_text(original)
        result = self.run_models_api_migration()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.config_path.read_text(), original)

    def test_models_api_migration_does_not_damage_invalid_json(self):
        self.config_path.write_text('{invalid json')
        result = self.run_models_api_migration()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.config_path.read_text(), '{invalid json')

    def test_router_rejects_nonlocal_host_and_wrong_port(self):
        for field, value in (('HOST', '0.0.0.0'), ('PORT', 3456)):
            with self.subTest(field=field):
                self.config_path.write_text(json.dumps({**self.config, field: value}))
                with self.assertRaisesRegex(SystemExit, 'HOST 127.0.0.1 and PORT 1455'):
                    ccodex.Router()

    def test_router_requires_installed_package(self):
        self.ccr.unlink()
        with self.assertRaisesRegex(SystemExit, 'Run ./run.sh arch-core'):
            ccodex.Router()

    def test_router_commands_use_system_node_and_propagate_exit(self):
        os.environ['PATH'] = '/old-node/bin:/usr/bin'
        router = ccodex.Router()
        with patch.object(ccodex.subprocess, 'run') as run:
            run.return_value.returncode = 0
            router.command('codex-auth')
            self.assertEqual(run.call_args.args[0], [str(self.ccr), 'codex-auth'])
            self.assertEqual(run.call_args.kwargs['env']['PATH'], '/usr/bin:/old-node/bin:/usr/bin')
            self.assertEqual(os.environ['PATH'], '/old-node/bin:/usr/bin')
            run.return_value.returncode = 5
            with self.assertRaises(SystemExit) as error:
                router.command('codex-auth')
        self.assertEqual(error.exception.code, 5)

    def test_request_sends_local_auth_and_json_body(self):
        router = ccodex.Router()
        router.config['APIKEY'] = 'test-local-key'
        with patch.object(ccodex.http.client, 'HTTPConnection') as connection:
            response = connection.return_value.getresponse.return_value
            response.status = 200
            response.read.return_value = b'{"type":"message"}'
            result = router.request('POST', '/v1/messages', {'model': 'codex,test'}, timeout=12)
        self.assertEqual(result, (200, {'type': 'message'}))
        connection.assert_called_once_with('127.0.0.1', 1455, timeout=12)
        args = connection.return_value.request.call_args.args
        self.assertEqual(args[:2], ('POST', '/v1/messages'))
        self.assertEqual(json.loads(args[2]), {'model': 'codex,test'})
        self.assertEqual(args[3]['Authorization'], 'Bearer test-local-key')
        self.assertEqual(args[3]['Content-Type'], 'application/json')
        connection.return_value.close.assert_called_once()

    def test_request_closes_connection_after_failure(self):
        with patch.object(ccodex.http.client, 'HTTPConnection') as connection:
            connection.return_value.request.side_effect = OSError('offline')
            with self.assertRaises(OSError):
                ccodex.Router().request('GET', '/health')
        connection.return_value.close.assert_called_once()

    def test_ready_checks_health_body(self):
        router = ccodex.Router()
        for result, expected in (((200, {'status': 'ok'}), True),
                                 ((200, {'status': 'other'}), False),
                                 ((200, 'not a router'), False), ((503, {}), False)):
            with self.subTest(result=result), patch.object(router, 'request', return_value=result):
                self.assertEqual(router.ready(), expected)
        for error in (OSError('offline'), http.client.HTTPException('bad response')):
            with patch.object(router, 'request', side_effect=error):
                self.assertFalse(router.ready())

    def test_start_reuses_ready_router(self):
        router = ccodex.Router()
        with patch.object(router, 'ready', return_value=True), patch.object(ccodex.subprocess, 'Popen') as popen:
            router.start()
        popen.assert_not_called()

    def test_start_waits_for_http_and_uses_private_log(self):
        router = ccodex.Router()
        with patch.object(router, 'ready', side_effect=[False, False, True]), \
                patch.object(ccodex.subprocess, 'Popen') as popen, patch.object(ccodex.time, 'sleep'):
            popen.return_value.poll.return_value = None
            router.start()
        self.assertEqual(popen.call_args.args[0], [str(self.ccr), 'start'])
        self.assertTrue(popen.call_args.kwargs['start_new_session'])
        self.assertTrue(popen.call_args.kwargs['env']['PATH'].startswith('/usr/bin:'))
        log = self.home / '.local/share/ccodex/server-start.log'
        self.assertEqual(log.stat().st_mode & 0o777, 0o600)

    def test_start_reports_early_exit(self):
        router = ccodex.Router()
        with patch.object(router, 'ready', return_value=False), patch.object(ccodex.subprocess, 'Popen') as popen:
            popen.return_value.poll.return_value = 3
            popen.return_value.returncode = 3
            with self.assertRaisesRegex(SystemExit, 'Router exited with code 3'):
                router.start()

    def test_start_has_bounded_wait(self):
        router = ccodex.Router()
        with patch.object(router, 'ready', return_value=False), \
                patch.object(ccodex.subprocess, 'Popen') as popen, patch.object(ccodex.time, 'sleep') as sleep:
            popen.return_value.poll.return_value = None
            with self.assertRaisesRegex(SystemExit, 'Router did not start'):
                router.start()
        self.assertEqual(sleep.call_count, 60)

    def test_sync_reloads_models_after_discovery(self):
        router = ccodex.Router()
        self.config['Providers'][0]['models'] = ['new-model']
        self.config_path.write_text(json.dumps(self.config))
        with patch.object(router, 'request', side_effect=[(200, {'models': ['old-model']}), (200, {})]) as request:
            router.sync_models()
        self.assertEqual(request.call_args.args, ('PUT', '/providers/codex', {'models': ['new-model']}))

    def test_sync_leaves_matching_registry_unchanged(self):
        router = ccodex.Router()
        with patch.object(router, 'request', return_value=(200, self.config['Providers'][0])) as request:
            router.sync_models()
        request.assert_called_once_with('GET', '/providers/codex')

    def test_sync_does_not_print_provider_credentials(self):
        router = ccodex.Router()
        with patch.object(router, 'request', return_value=(403, {'apiKey': 'never-print-this'})):
            with self.assertRaises(SystemExit) as error:
                router.sync_models()
        self.assertNotIn('never-print-this', str(error.exception))
        self.assertIn('HTTP 403', str(error.exception))

    def test_select_model_preserves_claude_arguments(self):
        args = ['--print', '--model', 'test-model', '--resume', 'session', 'prompt']
        self.assertEqual(ccodex.select_model(args, 'codex,default'),
                         ('codex,test-model', ['--print', '--resume', 'session', 'prompt']))

    def test_model_flag_can_select_each_supported_tier(self):
        for model in ('gpt-6-astra', 'gpt-6.1-sol', 'gpt-6-luna'):
            with self.subTest(model=model):
                self.assertEqual(ccodex.select_model(['--model', model], 'codex,gpt-6.1-sol'),
                                 ('codex,' + model, []))

    def test_model_flag_overrides_environment_and_last_flag_wins(self):
        os.environ['CCODEX_MODEL'] = 'from-env'
        self.assertEqual(ccodex.select_model([], 'codex,default'), ('codex,from-env', []))
        self.assertEqual(ccodex.select_model(['--model=first', '--model', 'codex,last'], 'codex,default'),
                         ('codex,last', []))

    def test_model_parsing_stops_at_separator(self):
        args = ['--', '--model', 'prompt-not-model', '--doctor']
        self.assertEqual(ccodex.select_model(args, 'codex,default'), ('codex,default', args))

    def test_invalid_model_flags_fail(self):
        for args in (['--model'], ['--model='], ['--model=other,model']):
            with self.subTest(args=args), self.assertRaises(SystemExit):
                ccodex.select_model(args, 'codex,default')

    def test_launch_env_routes_all_model_tiers_and_clears_credentials(self):
        os.environ.update({'ANTHROPIC_API_KEY': 'inherited-key', 'ANTHROPIC_CUSTOM_HEADERS': 'inherited-headers',
                           'CLAUDE_CODE_OAUTH_TOKEN': 'inherited-token', 'NO_PROXY': 'existing.example'})
        overrides = ccodex.launch_env(self.mock_router(), 'codex,test', {'max_input_tokens': 700000})
        for name in ('ANTHROPIC_MODEL', 'ANTHROPIC_SMALL_FAST_MODEL', 'CLAUDE_CODE_SUBAGENT_MODEL',
                     'ANTHROPIC_DEFAULT_OPUS_MODEL', 'ANTHROPIC_DEFAULT_SONNET_MODEL', 'ANTHROPIC_DEFAULT_HAIKU_MODEL'):
            self.assertEqual(overrides[name], 'codex,test')
        for name in ('ANTHROPIC_API_KEY', 'ANTHROPIC_CUSTOM_HEADERS', 'CLAUDE_CODE_OAUTH_TOKEN'):
            self.assertEqual(overrides[name], '')
        self.assertEqual(overrides['ANTHROPIC_BASE_URL'], 'http://127.0.0.1:1455')
        self.assertEqual(overrides['CLAUDE_CODE_MAX_CONTEXT_TOKENS'], '700000')
        self.assertEqual(overrides['NO_PROXY'], 'existing.example,localhost,127.0.0.1,::1')
        self.assertIn('127.0.0.1', overrides['no_proxy'])
        self.assertEqual(os.environ['ANTHROPIC_API_KEY'], 'inherited-key')

    def test_context_fallback_and_explicit_override(self):
        router = self.mock_router()
        self.assertEqual(ccodex.launch_env(router, 'codex,test', {})['CLAUDE_CODE_MAX_CONTEXT_TOKENS'], '200000')
        self.assertEqual(ccodex.launch_env(router, 'codex,test', {'context_window': 750000})[
            'CLAUDE_CODE_MAX_CONTEXT_TOKENS'], '750000')
        os.environ['CLAUDE_CODE_MAX_CONTEXT_TOKENS'] = '400000'
        self.assertEqual(ccodex.launch_env(router, 'codex,test', {})['CLAUDE_CODE_MAX_CONTEXT_TOKENS'], '400000')

    def test_help_needs_no_install_or_login(self):
        self.config_path.unlink()
        with contextlib.redirect_stdout(io.StringIO()) as output:
            ccodex.main(['--help'])
        self.assertIn('Usage: ccodex', output.getvalue())

    def test_missing_login_does_not_start_router(self):
        router = self.mock_router()
        with patch.object(ccodex, 'Router', return_value=router), self.assertRaisesRegex(SystemExit, 'ccodex --setup'):
            ccodex.main([])
        router.start.assert_not_called()

    def test_setup_logs_in_then_discovers_models(self):
        router = self.mock_router()
        router.command.side_effect = lambda *args: self.auth.touch() if args == ('codex-auth',) else None
        with patch.object(ccodex, 'Router', return_value=router), contextlib.redirect_stdout(io.StringIO()):
            ccodex.main(['--setup'])
        router.start.assert_called_once()
        self.assertEqual([call.args for call in router.command.call_args_list], [('codex-auth',), ('model', 'get', 'codex')])
        router.sync_models.assert_called_once()
        router.request.assert_not_called()

    def test_setup_reauthenticates_existing_login(self):
        self.auth.write_text('old credentials')
        router = self.mock_router()
        def command(*args):
            if args == ('codex-auth',):
                self.auth.write_text('new credentials')
        router.command.side_effect = command
        with patch.object(ccodex, 'Router', return_value=router), contextlib.redirect_stdout(io.StringIO()):
            ccodex.main(['--setup'])
        self.assertEqual([call.args for call in router.command.call_args_list],
                         [('codex-auth',), ('model', 'get', 'codex')])
        router.sync_models.assert_called_once()
        self.assertEqual(self.auth.read_text(), 'new credentials')

    def test_setup_rejects_unchanged_stale_credentials(self):
        self.auth.write_text('stale credentials')
        router = self.mock_router()
        with patch.object(ccodex, 'Router', return_value=router), \
                self.assertRaisesRegex(SystemExit, 'did not update Codex credentials'):
            ccodex.main(['--setup'])
        self.assertEqual(self.auth.read_text(), 'stale credentials')
        router.command.assert_called_once_with('codex-auth')
        router.sync_models.assert_not_called()

    def test_setup_checks_that_login_completed(self):
        router = self.mock_router()
        with patch.object(ccodex, 'Router', return_value=router), self.assertRaisesRegex(SystemExit, 'did not complete'):
            ccodex.main(['--setup'])
        router.sync_models.assert_not_called()

    def test_auth_always_runs_browser_login(self):
        self.auth.write_text('old credentials')
        router = self.mock_router()
        router.command.side_effect = lambda *args: self.auth.write_text('new credentials')
        with patch.object(ccodex, 'Router', return_value=router), contextlib.redirect_stdout(io.StringIO()):
            ccodex.main(['--auth'])
        router.command.assert_called_once_with('codex-auth')
        router.sync_models.assert_not_called()
        self.assertEqual(self.auth.read_text(), 'new credentials')

    def test_launch_sets_cli_settings_without_changing_user_files(self):
        self.auth.touch()
        settings_path = self.home / '.claude/settings.json'
        settings_path.parent.mkdir()
        original = '{"env":{"ANTHROPIC_BASE_URL":"https://existing.example"},"hooks":{}}'
        settings_path.write_text(original)
        router = self.mock_router()
        with patch.object(ccodex, 'Router', return_value=router), \
                patch.object(ccodex.shutil, 'which', return_value='/usr/bin/claude'), patch.object(ccodex.os, 'execv') as execv:
            ccodex.main(['--model=test-model', '--print', 'hello'])
        command, argv = execv.call_args.args
        self.assertEqual(command, '/usr/bin/claude')
        settings = json.loads(argv[2])
        self.assertTrue(settings['disableClaudeAiConnectors'])
        overrides = settings['env']
        self.assertEqual(argv[3:], ['--model', 'codex,test-model', '--print', 'hello'])
        self.assertEqual(overrides['ANTHROPIC_BASE_URL'], 'http://127.0.0.1:1455')
        self.assertEqual(overrides['ANTHROPIC_DEFAULT_HAIKU_MODEL'], 'codex,test-model')
        self.assertEqual(os.environ['ANTHROPIC_BASE_URL'], overrides['ANTHROPIC_BASE_URL'])
        self.assertEqual(settings_path.read_text(), original)
        self.assertEqual(json.loads(self.config_path.read_text()), self.config)
        router.request.assert_called_once_with('GET', '/v1/models/codex%2Ctest-model')

    def test_invalid_model_never_launches_claude(self):
        self.auth.touch()
        router = self.mock_router()
        router.request.return_value = (404, {'error': {'message': 'model not found'}})
        with patch.object(ccodex, 'Router', return_value=router), patch.object(ccodex.os, 'execv') as execv:
            with self.assertRaisesRegex(SystemExit, 'Router rejected'):
                ccodex.main(['--model=invalid'])
        execv.assert_not_called()

    def test_doctor_is_the_only_launch_path_sending_inference(self):
        self.auth.touch()
        router = self.mock_router()
        router.request.side_effect = [(200, {}), (200, {'type': 'message'})]
        with patch.object(ccodex, 'Router', return_value=router), patch.object(ccodex.os, 'execv') as execv, \
                contextlib.redirect_stdout(io.StringIO()) as output:
            ccodex.main(['--doctor', '--model=test'])
        self.assertIn('Subscription inference succeeded', output.getvalue())
        self.assertEqual(router.request.call_args.args[:2], ('POST', '/v1/messages'))
        self.assertEqual(router.request.call_args.args[2]['model'], 'codex,test')
        self.assertEqual(router.request.call_args.kwargs['timeout'], 120)
        execv.assert_not_called()

    def test_doctor_explains_invalidated_refresh_token(self):
        self.auth.touch()
        router = self.mock_router()
        router.request.side_effect = [(200, {}), (500, {
            'error': {'message': 'Codex OAuth token refresh failed (401): refresh_token_invalidated',
                      'code': 'internal_error'}})]
        with patch.object(ccodex, 'Router', return_value=router), \
                self.assertRaisesRegex(SystemExit, 'ccodex --setup'):
            ccodex.main(['--doctor'])
        self.assertEqual(router.request.call_count, 2)

    def test_doctor_reports_failed_inference(self):
        self.auth.touch()
        router = self.mock_router()
        router.request.side_effect = [(200, {}), (401, {'error': 'expired login'})]
        with patch.object(ccodex, 'Router', return_value=router), self.assertRaisesRegex(SystemExit, 'expired login'):
            ccodex.main(['--doctor'])


if __name__ == '__main__':
    unittest.main()
