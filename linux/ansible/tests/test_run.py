"""Exercise the real provisioning entry point without sudo, network or Ansible."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class RunFlow(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.log = self.directory / 'commands.jsonl'
        binaries = self.directory / 'bin'
        binaries.mkdir()
        for tool in ['sudo', 'ansible-galaxy', 'ansible-playbook']:
            stub = binaries / tool
            stub.write_text(f'''#!{sys.executable}
import json,os,sys
from pathlib import Path
with open(os.environ['RUN_FLOW_LOG'], 'a') as stream:
    stream.write(json.dumps([Path(sys.argv[0]).name, *sys.argv[1:]]) + '\\n')
if Path(sys.argv[0]).name == 'sudo' and sys.argv[1:3] == ['-n', '-v']:
    sys.exit(1)
''')
            stub.chmod(0o700)
        for playbook in ['arch-core', 'arch-desktop', 'arch-home']:
            (self.directory / (playbook + '.yml')).touch()
        (self.directory / 'roles').mkdir()
        (self.directory / 'roles/requirements.yml').touch()
        self.environment = dict(os.environ, PATH=str(binaries) + os.pathsep + os.environ['PATH'],
                                RUN_FLOW_LOG=str(self.log))

    def run_flow(self, *args):
        result = subprocess.run(['bash', str(ROOT / 'run.sh'), *args], cwd=self.directory,
                                env=self.environment, capture_output=True, text=True, timeout=5)
        commands = [json.loads(line) for line in self.log.read_text().splitlines()] if self.log.exists() else []
        return result, commands

    def test_normal_playbooks_preserve_the_existing_invocation(self):
        for playbook in ['arch-core', 'arch-desktop', 'arch-home']:
            with self.subTest(playbook=playbook):
                self.log.unlink(missing_ok=True)
                result, commands = self.run_flow(playbook)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual([c for c in commands if c[0] == 'ansible-playbook'],
                                 [['ansible-playbook', '-v', playbook + '.yml']])
                self.assertIn(['ansible-galaxy', 'collection', 'install', '-r',
                               'roles/requirements.yml', '--upgrade'], commands)

    def test_corporate_option_reaches_each_normal_playbook(self):
        for playbook in ['arch-core', 'arch-desktop', 'arch-home']:
            with self.subTest(playbook=playbook):
                self.log.unlink(missing_ok=True)
                result, commands = self.run_flow(playbook, '--corporate')
                self.assertEqual(result.returncode, 0, result.stderr)
                invocation = next(c for c in commands if c[0] == 'ansible-playbook')
                self.assertEqual(invocation[:4], ['ansible-playbook', '-v', playbook + '.yml', '--extra-vars'])
                self.assertEqual(json.loads(invocation[4]), {'codex_corporate_enabled': True})

    def test_invalid_options_fail_before_authentication_or_provisioning(self):
        for args in [[], ['other'], ['arch-core', '--unknown'], ['arch-core', '--corporate', '--unknown']]:
            with self.subTest(args=args):
                result, commands = self.run_flow(*args)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(commands, [])


if __name__ == '__main__':
    unittest.main()
