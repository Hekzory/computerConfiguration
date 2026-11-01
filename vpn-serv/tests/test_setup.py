import contextlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('remote', ROOT / 'remote.py')
remote = importlib.util.module_from_spec(spec)
spec.loader.exec_module(remote)


class RemoteTests(unittest.TestCase):
    def test_qdisc_check_apply_repeat_preserves_custom_hierarchy(self):
        kinds = {'ens3': 'fq', 'ens4': 'htb'}
        mutations = []

        def network(argv, **kwargs):
            if argv[0] == 'ip':
                result = [{'dev': 'ens3'}, {'dev': 'ens4'}]
            elif 'replace' in argv:
                device = argv[4]
                mutations.append(device)
                kinds[device] = 'fq_codel'
                return subprocess.CompletedProcess(argv, 0, '', '')
            else:
                result = [{'kind': kinds[argv[-1]], 'root': True}]
            return subprocess.CompletedProcess(argv, 0, json.dumps(result), '')

        with patch.object(remote, 'command', side_effect=network), contextlib.redirect_stdout(io.StringIO()) as output:
            remote.configure_qdisc(False)
            self.assertEqual(mutations, [])
            remote.configure_qdisc(True)
            remote.configure_qdisc(True)
            self.assertEqual(mutations, ['ens3'])
            self.assertEqual(kinds['ens4'], 'htb')
            self.assertIn('WARN', output.getvalue())

    def test_network_defaults_persist_and_repair_live_drift(self):
        current = dict(remote.SYSCTL)
        current['net.ipv4.tcp_congestion_control'] = 'hybla'
        current['fs.file-max'] = '51200'
        current['net.core.default_qdisc'] = 'fq'
        commands = []
        def execute(argv, **kwargs):
            commands.append(argv)
            if argv[:2] == ['sysctl', '-n']:
                return subprocess.CompletedProcess(argv, 0, current[argv[2]] + '\n', '')
            if argv[:2] == ['sysctl', '-w']:
                key, value = argv[2].split('=', 1)
                current[key] = value
            return subprocess.CompletedProcess(argv, 0, '', '')
        with patch.object(remote, 'command', side_effect=execute), \
             patch.object(remote.Settings, 'write', return_value=False) as write, \
             patch.object(remote, 'resolve_sysctl_conflicts'), patch.object(remote, 'configure_qdisc'), \
             contextlib.redirect_stdout(io.StringIO()):
            remote.configure(False)
            self.assertEqual(current['net.ipv4.tcp_congestion_control'], 'hybla')
            self.assertFalse(any(c[:2] == ['sysctl', '-w'] for c in commands))
            self.assertTrue(all('--dry-run' in c for c in commands if c[0] == 'modprobe'))
            commands.clear()
            remote.configure(True)
            self.assertEqual(current, remote.SYSCTL)
            self.assertLess(commands.index(['modprobe', 'tcp_bbr']),
                            commands.index(['sysctl', '-w', 'net.ipv4.tcp_congestion_control=bbr']))
            files = {c.args[0]: c.args[1] for c in write.call_args_list}
            self.assertIn('tcp_bbr\n', files['/etc/modules-load.d/90-vpn-serv.conf'])
            self.assertIn('net.ipv4.tcp_congestion_control = bbr\n', files['/etc/sysctl.d/90-vpn-serv.conf'])
            commands.clear()
            remote.configure(True)
            self.assertFalse(any(c[:2] == ['sysctl', '-w'] for c in commands))

    def test_stale_failure_check_apply_and_repeat(self):
        failed = True
        mutations = []

        def systemctl(argv, **kwargs):
            nonlocal failed
            if '--failed' in argv:
                self.assertEqual(argv[1], 'list-units')
                output = 'apport.service not-found failed failed apport\n' if failed else ''
            elif argv[1] == 'reset-failed':
                mutations.append(argv)
                failed = False
                output = ''
            elif '--value' in argv:
                output = 'inactive\n'
            else:
                output = 'LoadState=not-found\nActiveState=failed\n'
            return subprocess.CompletedProcess(argv, 0, output, '')

        with patch.object(remote, 'command', side_effect=systemctl), contextlib.redirect_stdout(io.StringIO()) as out:
            remote.report_failed_services(cleanup=True, apply=False)
            self.assertEqual(mutations, [])
            self.assertIn('PLAN', out.getvalue())
            self.assertNotIn('WARN', out.getvalue())
            remote.report_failed_services(cleanup=True, apply=True)
            self.assertEqual(mutations, [['systemctl', 'reset-failed', 'apport.service']])
            remote.report_failed_services(cleanup=True, apply=True)
            self.assertEqual(len(mutations), 1)

    def test_loaded_and_unrelated_failures_preserved(self):
        responses = [subprocess.CompletedProcess([], 0,
                     'apport.service loaded failed failed apport\nssh.service not-found failed failed ssh\n', ''),
                     subprocess.CompletedProcess([], 0, 'LoadState=loaded\nActiveState=failed\n', '')]
        with patch.object(remote, 'command', side_effect=responses) as cmd, contextlib.redirect_stdout(io.StringIO()) as out:
            remote.report_failed_services(cleanup=True, apply=True)
            self.assertFalse(any('reset-failed' in call.args[0] for call in cmd.call_args_list))
            events = [json.loads(line) for line in out.getvalue().splitlines()]
            self.assertEqual(events[0]['message'], 'Сбой служб: apport.service, ssh.service')

    def test_masked_timer_failure_is_cleared(self):
        responses = [subprocess.CompletedProcess([], 0, 'man-db.timer masked failed failed man-db\n', ''),
                     subprocess.CompletedProcess([], 0, 'LoadState=masked\nActiveState=failed\n', ''),
                     subprocess.CompletedProcess([], 0, '', ''),
                     subprocess.CompletedProcess([], 0, '', '')]
        with patch.object(remote, 'command', side_effect=responses) as cmd, contextlib.redirect_stdout(io.StringIO()) as out:
            remote.report_failed_services(cleanup=True, apply=True)
            self.assertIn(unittest.mock.call(['systemctl', 'reset-failed', 'man-db.timer']), cmd.call_args_list)
            self.assertEqual(cmd.call_args.args[0], ['systemctl', 'list-units', '--failed',
                             '--no-legend', '--plain', '--no-pager', 'man-db.timer'])
            self.assertIn('CHANGED', out.getvalue())
            self.assertNotIn('WARN', out.getvalue())

    def test_no_cleanup_without_debloat(self):
        with patch.object(remote, 'command', return_value=subprocess.CompletedProcess(
                [], 0, 'apport.service not-found failed failed apport\n', '')) as cmd, \
                contextlib.redirect_stdout(io.StringIO()) as out:
            remote.report_failed_services()
            self.assertEqual(cmd.call_count, 1)
            self.assertIn('WARN', out.getvalue())

    def test_reject_other_os_before_any_command(self):
        with patch.object(remote, 'ubuntu', side_effect=RuntimeError('not Ubuntu')), patch.object(remote, 'command') as cmd:
            with self.assertRaises(RuntimeError):
                remote.main({'mode': 'apply'})
            cmd.assert_not_called()

    def test_os_detection_exact_id(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'os-release'
            path.write_text('ID=ubuntu\nPRETTY_NAME="Ubuntu 24.04 LTS"\n')
            self.assertEqual(remote.ubuntu(path), 'Ubuntu 24.04 LTS')
            path.write_text('ID=linuxmint\nID_LIKE=ubuntu\n')
            with self.assertRaises(RuntimeError):
                remote.ubuntu(path)

    def test_package_allowlist_preserves_infrastructure(self):
        self.assertEqual(remote.package_plan(['docker-ce', 'cloud-init', 'openssh-server',
                         'systemd-resolved', 'snapd', 'cups', 'apport']), ['apport', 'cups'])

    def test_dependency_removal_refused(self):
        with self.assertRaises(RuntimeError):
            remote.simulated_removals('Purg cups [1.0]\nRemv important-service [2.0]', ['cups'])

    def test_package_installation_refused(self):
        with self.assertRaises(RuntimeError):
            remote.simulated_removals('Purg cups [1.0]\nInst unexpected [2.0]', ['cups'])

    def test_exact_plan_accepted(self):
        self.assertEqual(remote.simulated_removals('Purg cups [1.0]\n', ['cups']), ['cups'])

    def test_changed_plan_refused(self):
        with self.assertRaises(RuntimeError):
            remote.simulated_removals('', ['cups'])

    def test_ubuntu_server_debloat_plan_and_purge(self):
        packages = ['ubuntu-server-minimal', 'apport', 'apport-core-dump-handler',
                    'modemmanager', 'ubuntu-server']
        simulation = ''.join(f'Purg {name} [1.0]\n' for name in packages)
        responses = [
            subprocess.CompletedProcess([], 0, 'apport\tinstalled\nmodemmanager\tinstalled\n', ''),
            subprocess.CompletedProcess([], 0, simulation, ''),
            subprocess.CompletedProcess([], 0, simulation, ''),
            subprocess.CompletedProcess([], 0, '', ''),
        ]
        output = io.StringIO()
        with patch.object(remote, 'ubuntu', return_value='Ubuntu'), \
             patch.object(remote.os, 'geteuid', return_value=0), \
             patch.object(remote.Path, 'is_dir', return_value=True), \
             patch.object(remote, 'inspect'), patch.object(remote, 'report_failed_services'), patch.object(remote, 'disable_services'), patch.object(remote, 'configure'), \
             patch.object(remote, 'command', side_effect=responses) as cmd, \
             contextlib.redirect_stdout(output):
            remote.main({'mode': 'check', 'debloat': True})
            events = [json.loads(line) for line in output.getvalue().splitlines()]
            approved = next(event['packages'] for event in events if event['status'] == 'PACKAGES')
            self.assertEqual(approved, packages)
            self.assertTrue(any(event['status'] == 'WARN' for event in events))
            self.assertTrue(all('-y' not in call.args[0] for call in cmd.call_args_list))
            remote.main({'mode': 'purge', 'packages': approved})
            self.assertEqual(cmd.call_args.args[0],
                             ['apt-get', '-y', '--no-auto-remove', 'purge', '--', *packages])

    def test_metapackages_not_selected_directly(self):
        self.assertEqual(remote.package_plan(['ubuntu-server', 'ubuntu-server-minimal']), [])

    def test_expansion_still_rejects_unexpected_packages_and_missing_targets(self):
        for output in ('Purg apport [1]\nRemv openssh-server [1]\n',
                       'Purg ubuntu-server [1]\n',
                       'Purg apport [1]\nInst unexpected [1]\n'):
            with self.subTest(output=output), self.assertRaises(RuntimeError):
                remote.simulated_removals(output, ['apport'], expand=True)

    def test_known_extra_package_after_confirmation_is_rejected(self):
        with self.assertRaises(RuntimeError):
            remote.simulated_removals('Purg apport [1]\nPurg ubuntu-server [1]\n', ['apport'])

    def test_sysctl_conflict_symlink_backup_and_repeat(self):
        with tempfile.TemporaryDirectory() as folder, contextlib.redirect_stdout(io.StringIO()) as output:
            etc = Path(folder) / 'etc'
            (etc / 'sysctl.d').mkdir(parents=True)
            original = '# keep me\nnet.ipv4.tcp_syncookies = 0\nnet.ipv4.ip_forward = 1\n'
            target = etc / 'sysctl.conf'
            target.write_text(original)
            target.chmod(0o640)
            alias = etc / 'sysctl.d/99-sysctl.conf'
            alias.symlink_to('../sysctl.conf')
            remote.resolve_sysctl_conflicts(remote.Settings(False), remote.SYSCTL, etc)
            self.assertEqual(target.read_text(), original)
            events = [json.loads(line) for line in output.getvalue().splitlines()]
            self.assertEqual(sum(event['status'] == 'PLAN' for event in events), 1)
            settings = remote.Settings(True)
            settings.backup = Path(folder) / 'backup'
            remote.resolve_sysctl_conflicts(settings, remote.SYSCTL, etc)
            self.assertTrue(alias.is_symlink())
            self.assertIn('# vpn-serv:', target.read_text())
            self.assertIn('\nnet.ipv4.ip_forward = 1\n', target.read_text())
            self.assertEqual(target.stat().st_mode & 0o777, 0o640)
            self.assertEqual((settings.backup / str(target).lstrip('/')).read_text(), original)
            output.truncate(0)
            output.seek(0)
            remote.resolve_sysctl_conflicts(settings, remote.SYSCTL, etc)
            self.assertEqual(output.getvalue(), '')

    def test_sysctl_slash_syntax_and_external_symlink(self):
        with tempfile.TemporaryDirectory() as folder, contextlib.redirect_stdout(io.StringIO()) as output:
            etc = Path(folder) / 'etc'
            (etc / 'sysctl.d').mkdir(parents=True)
            outside = Path(folder) / 'vendor.conf'
            outside.write_text('-net/ipv4/tcp_syncookies = 0\n')
            (etc / 'sysctl.d/99-vendor.conf').symlink_to(outside)
            remote.resolve_sysctl_conflicts(remote.Settings(True), remote.SYSCTL, etc)
            self.assertEqual(outside.read_text(), '-net/ipv4/tcp_syncookies = 0\n')
            self.assertIn('WARN', output.getvalue())

    def test_services_check_apply_repeat_and_protected_units(self):
        states = {'motd-news.timer': ('enabled', 'active'),
                  'packagekit.service': ('static', 'inactive')}
        calls = []

        def systemctl(argv, **kwargs):
            calls.append(argv)
            if argv[1] == 'list-unit-files':
                output = '\n'.join(f'{name} {state[0]}' for name, state in states.items())
                output += '\ndocker.service enabled\nssh.service enabled\napt-daily.timer enabled\ncloud-init.service enabled\n'
            elif argv[1] == 'show':
                enabled, active = states[argv[2]]
                output = f'UnitFileState={enabled}\nActiveState={active}\n'
            elif argv[1] == 'mask':
                self.assertEqual(argv[2], '--now')
                states[argv[3]] = ('masked', 'inactive')
                output = ''
            else:
                self.fail(argv)
            return subprocess.CompletedProcess(argv, 0, output, '')

        with patch.object(remote, 'command', side_effect=systemctl), contextlib.redirect_stdout(io.StringIO()):
            remote.disable_services(False)
            self.assertFalse(any(call[1] == 'mask' for call in calls))
            remote.disable_services(True)
            masks = [call for call in calls if call[1] == 'mask']
            self.assertEqual(len(masks), 2)
            remote.disable_services(True)
            self.assertEqual(len([call for call in calls if call[1] == 'mask']), 2)

    def test_service_stop_failure_is_not_reported_as_success(self):
        results = [subprocess.CompletedProcess([], 0, 'motd-news.timer enabled\n', ''),
                   subprocess.CompletedProcess([], 0, 'UnitFileState=enabled\nActiveState=active\n', ''),
                   RuntimeError('cannot stop')]
        with patch.object(remote, 'command', side_effect=results), contextlib.redirect_stdout(io.StringIO()) as output:
            with self.assertRaisesRegex(RuntimeError, 'cannot stop'):
                remote.disable_services(True)
            self.assertNotIn('CHANGED', output.getvalue())

    def test_check_creates_no_files(self):
        with tempfile.TemporaryDirectory() as folder, contextlib.redirect_stdout(io.StringIO()):
            path = Path(folder) / 'missing' / 'config'
            self.assertTrue(remote.Settings(False).write(str(path), 'new'))
            self.assertFalse(path.parent.exists())

    def test_write_backup_and_idempotence(self):
        with tempfile.TemporaryDirectory() as folder, contextlib.redirect_stdout(io.StringIO()):
            path = Path(folder) / 'config'
            path.write_text('old')
            settings = remote.Settings(True)
            settings.backup = Path(folder) / 'backups'
            self.assertTrue(settings.write(str(path), 'new'))
            self.assertEqual(path.read_text(), 'new')
            self.assertEqual((settings.backup / str(path).lstrip('/')).read_text(), 'old')
            self.assertFalse(settings.write(str(path), 'new'))
            self.assertEqual((settings.backup / str(path).lstrip('/')).read_text(), 'old')

    def test_symlink_refused(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'config'
            path.symlink_to('/nonexistent')
            with self.assertRaises(RuntimeError):
                remote.Settings(True).write(str(path), 'new')

    def test_audit_uses_read_only_configuration_and_services(self):
        with patch.object(remote, 'ubuntu', return_value='Ubuntu'), \
             patch.object(remote.os, 'geteuid', return_value=0), \
             patch.object(remote.Path, 'is_dir', return_value=True), \
             patch.object(remote, 'inspect'), patch.object(remote, 'report_failed_services'), patch.object(remote, 'disable_services') as services, patch.object(remote, 'configure') as configure, \
             patch.object(remote, 'command', return_value=subprocess.CompletedProcess([], 0, 'docker-ce\tinstalled\n', '')), \
             contextlib.redirect_stdout(io.StringIO()):
            remote.main({'mode': 'audit'})
            configure.assert_called_once_with(False)
            services.assert_called_once_with(False)


class CLITests(unittest.TestCase):
    def test_concise_and_verbose_output(self):
        import runpy
        Reporter = runpy.run_path(str(ROOT / 'setup'))['Reporter']
        events = [{'status': key, 'message': message} for key, message in
                  [('OK', 'unchanged detail'), ('DETAIL', 'APT long output'),
                   ('INFO', 'RAM summary'), ('CHANGED', 'fixed sysctl'), ('WARN', 'restart needed')]]
        with contextlib.redirect_stdout(io.StringIO()) as output:
            reporter = Reporter()
            for event in events:
                reporter.event(event)
            reporter.summary()
        self.assertNotIn('unchanged detail', output.getvalue())
        self.assertNotIn('APT long output', output.getvalue())
        self.assertIn('RAM summary', output.getvalue())
        self.assertIn('fixed sysctl', output.getvalue())
        self.assertIn('restart needed', output.getvalue())
        self.assertIn('Уже настроено: 1', output.getvalue())
        with contextlib.redirect_stdout(io.StringIO()) as output:
            reporter = Reporter(verbose=True)
            for event in events:
                reporter.event(event)
        self.assertIn('unchanged detail', output.getvalue())
        self.assertIn('APT long output', output.getvalue())

    def test_saved_host_from_another_directory_and_explicit_override(self):
        import os
        import shutil
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            app = directory / 'app'
            app.mkdir()
            for name in ('setup', 'remote.py'):
                shutil.copy2(ROOT / name, app / name)
            record = directory / 'record'
            ssh = directory / 'ssh'
            ssh.write_text('#!/usr/bin/env python3\nimport json, os, sys\n'
                           'from pathlib import Path\n'
                           'sys.stdin.read()\n'
                           'Path(os.environ["SSH_RECORD"]).write_text(json.dumps(sys.argv[1:]))\n')
            ssh.chmod(0o755)
            env = {**os.environ, 'PATH': folder + ':' + os.environ['PATH'], 'SSH_RECORD': str(record)}

            def run(*args):
                return subprocess.run([str(app / 'setup'), *args], cwd=folder,
                                      env=env, capture_output=True, text=True)

            self.assertEqual(run('--check').returncode, 2)
            self.assertFalse(record.exists())
            self.assertEqual(run('set', 'user@first').returncode, 0)
            self.assertFalse(record.exists())
            saved = app / '.last-host'
            self.assertEqual(saved.read_text(), 'user@first\n')
            self.assertEqual(saved.stat().st_mode & 0o777, 0o600)
            self.assertEqual(run('--check').returncode, 0)
            self.assertIn('user@first', json.loads(record.read_text()))
            self.assertEqual(run('user@override', '--audit').returncode, 0)
            self.assertIn('user@override', json.loads(record.read_text()))
            self.assertEqual(saved.read_text(), 'user@first\n')
            self.assertEqual(run('set', 'user@second').returncode, 0)
            self.assertEqual(run('--check').returncode, 0)
            self.assertIn('user@second', json.loads(record.read_text()))
            self.assertEqual(run('set', '--', '-oBadOption').returncode, 2)
            self.assertEqual(saved.read_text(), 'user@second\n')
            saved.write_text('')
            self.assertEqual(run('--check').returncode, 2)
            saved.unlink()
            self.assertEqual(run('--check').returncode, 2)

    def test_help(self):
        result = subprocess.run([str(ROOT / 'setup'), '--help'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0)
        self.assertIn('--debloat', result.stdout)

    def test_invalid_target_before_ssh(self):
        result = subprocess.run([str(ROOT / 'setup'), '--', '-oProxyCommand=bad'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn('invalid SSH destination', result.stderr)

    def test_ssh_payload_and_noninteractive_debloat(self):
        import os
        with tempfile.TemporaryDirectory() as folder:
            ssh = Path(folder) / 'ssh'
            record = Path(folder) / 'record'
            ssh.write_text('#!/usr/bin/env python3\nimport json, os, sys\n'
                           'from pathlib import Path\n'
                           'Path(os.environ["SSH_RECORD"]).write_text(json.dumps(sys.argv[1:]))\n'
                           'assert "def configure" in sys.stdin.read()\n'
                           'print(json.dumps(dict(status="PACKAGES", message="", packages=["cups"])))\n')
            ssh.chmod(0o755)
            result = subprocess.run([str(ROOT / 'setup'), 'user@host', '--debloat'], input='',
                                    capture_output=True, text=True,
                                    env={**os.environ, 'PATH': folder + ':' + os.environ['PATH'], 'SSH_RECORD': str(record)})
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('Удаление пропущено', result.stdout)
            arguments = json.loads(record.read_text())
            self.assertIn('BatchMode=yes', arguments)
            self.assertIn('user@host', arguments)
            self.assertIn('sudo -n', arguments[-1])


if __name__ == '__main__':
    unittest.main()
