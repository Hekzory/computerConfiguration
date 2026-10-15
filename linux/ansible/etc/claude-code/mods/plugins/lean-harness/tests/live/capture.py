#!/usr/bin/env python3
"""Captures what a logged-in Claude Code composes, offers and lists, as a fixture for the unit tests.

Run it after a Claude Code update on a machine signed in to claude.ai: the headless check in CI
sees neither the account's server-side prompt variants nor its claude.ai skills, the fixtures do.
It starts one interactive session with the probe seated by policy (in a user and mount namespace,
no root; lean-harness, the skill overrides and the Claude Docs deny left out so everything comes as
shipped), sends one short Haiku prompt and
writes tests/fixtures/v<version>.ts plus tests/fixtures/index.ts. The home folder, user name and
any e-mail address are replaced before writing: this repository is public.

    python3 capture.py [--claude PATH] [--model claude-haiku-5-5]
"""

import argparse
import getpass
import json
import os
import pty
import re
import select
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
TESTS = HERE.parent
FIXTURES = TESTS / 'fixtures'
REPO = TESTS.parents[7]
ETC = Path('/etc/claude-code')
PERSONAL = '10-claude-personal.json'
DOCS = {'serverName': 'claude.ai Claude Docs'}
SEAT = {
    'extraKnownMarketplaces': {'lean-harness-tests': {'source': {'source': 'directory', 'path': str(HERE)}}},
    'enabledPlugins': {'probe@lean-harness-tests': True},
    'prependPlugins': ['probe@lean-harness-tests', 'sec-default@builtin'],
}


def die(msg):
    print(f'capture: {msg}', file=sys.stderr)
    sys.exit(1)


def managed_dir(tmp):
    """The machine's policy minus what this repo trims with, plus the probe's seat."""
    out = tmp / 'etc-claude-code'
    (out / 'managed-settings.d').mkdir(parents=True)
    if (ETC / 'managed-settings.json').is_file():
        shutil.copy(ETC / 'managed-settings.json', out)
    for f in sorted((ETC / 'managed-settings.d').glob('*.json')) if (ETC / 'managed-settings.d').is_dir() else []:
        if f.name == PERSONAL:
            personal = json.loads(f.read_text())
            personal.pop('skillOverrides', None)
            denied = [d for d in personal.pop('deniedMcpServers', []) if d != DOCS]
            if denied:
                personal['deniedMcpServers'] = denied
            (out / 'managed-settings.d' / f.name).write_text(json.dumps(personal, indent=2))
        elif f.name != '40-claude-lean-harness.json':
            shutil.copy(f, out / 'managed-settings.d')
    (out / 'managed-settings.d' / '99-lean-harness-capture.json').write_text(json.dumps(SEAT, indent=2))
    return out


def session(claude, model, etc, probe_out):
    """One interactive session: waits for the probe's start snapshot, asks one thing, quits."""
    env = {k: v for k, v in os.environ.items() if not k.startswith('CLAUDE_CODE_') and k not in ('CLAUDECODE', 'CLAUDE_PID', 'CLAUDE_EFFORT')}
    env['PROBE_OUT'] = str(probe_out)
    argv = ['unshare', '--user', '--map-root-user', '--mount', 'sh', '-c', 'mount --rbind "$1" /etc/claude-code && shift && exec "$@"',
            'sh', str(etc), claude, '--model', model]
    pid, fd = pty.fork()
    if pid == 0:
        os.chdir(REPO)
        os.execvpe(argv[0], argv, env)
    screen = b''

    def pump(seconds, until=None):
        nonlocal screen
        end = time.time() + seconds
        while time.time() < end and not (until and until()):
            ready, _, _ = select.select([fd], [], [], 0.3)
            if ready:
                try:
                    screen += os.read(fd, 65536)
                except OSError:
                    return

    try:
        pump(45, lambda: (probe_out / 'session.json').exists())
        if not (probe_out / 'session.json').exists():
            text = re.sub(rb'\x1b\[[0-9;?<>=]*[a-zA-Z~]', b'', screen).decode('utf8', 'replace')
            die(f'the session never started (a dialog?); last screen:\n{text[-1500:]}')
        pump(15, lambda: (probe_out / 'late.json').exists())
        os.write(fd, b'Reply with just: ok')
        pump(1)
        os.write(fd, b'\r')
        pump(120, lambda: (probe_out / 'done').exists())
        if not (probe_out / 'done').exists():
            die('the request never completed')
        pump(2)
    finally:
        for _ in range(3):
            try:
                os.write(fd, b'\x03')
            except OSError:
                break
            pump(0.5)
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass


def scrub(text):
    home = str(Path.home())
    user = getpass.getuser()
    text = text.replace(home, '/home/user').replace(home.replace('/', '-'), '-home-user')
    text = re.sub(r'[\w.+-]+@[\w-]+\.[\w.-]+', 'user@example.com', text)
    return re.sub(rf'\b{re.escape(user)}\b', 'user', text) if len(user) > 2 else text


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('--claude', default=shutil.which('claude'))
    ap.add_argument('--model', default='claude-haiku-5-5')
    a = ap.parse_args()
    if not a.claude:
        die('no claude on PATH')
    version = subprocess.run([a.claude, '--version'], capture_output=True, text=True).stdout.split()[0]
    if subprocess.run(['unshare', '--user', '--map-root-user', '--mount', 'true']).returncode != 0 or not ETC.is_dir():
        die('needs user namespaces and an /etc/claude-code to mount over')

    with tempfile.TemporaryDirectory(prefix='lean-harness-capture-') as tmp:
        tmp = Path(tmp)
        probe_out = tmp / 'probe'
        probe_out.mkdir()
        session(a.claude, a.model, managed_dir(tmp), probe_out)
        start = json.loads((probe_out / 'session.json').read_text())
        late = json.loads((probe_out / 'late.json').read_text())
        events = json.loads((probe_out / 'events.json').read_text())

    request = events['compose'][0] if events['compose'] else {}
    fixture = {
        'version': version,
        'captured': datetime.now(timezone.utc).strftime('%Y-%m-%d'),
        'model': a.model,
        'sections': late['compose'] or start['compose'],
        'requestTools': request.get('tools', []),
        'commands': late.get('commands') or start.get('commands', []),
        'tools': events['tools'],
        'agents': events['agents'],
        'attachments': {k: v['raw'] for k, v in events['attachments'].items()},
    }
    missing = [k for k in ('skill_listing', 'agent_listing_delta', 'total_tokens_reminder') if k not in fixture['attachments']]
    if missing or not fixture['tools'] or not fixture['agents']:
        die(f'incomplete capture: missing {missing or "tool or agent events"}')

    FIXTURES.mkdir(exist_ok=True)
    name = f'v{version}.ts'
    body = scrub(json.dumps(fixture, indent=1, ensure_ascii=False))
    (FIXTURES / name).write_text(
        f'// What Claude Code {version} composed, offered and listed for a logged-in interactive session on\n'
        f'// {fixture["captured"]}, as shipped (lean-harness left out). Written by tests/live/capture.py.\n'
        f'export const FIXTURE = {body}\n')

    def key(p):
        return tuple(int(x) for x in re.findall(r'\d+', p.stem))
    files = sorted(FIXTURES.glob('v*.ts'), key=key)
    idents = [f'v{"_".join(re.findall(r"[0-9]+", f.stem))}' for f in files]
    (FIXTURES / 'index.ts').write_text(
        '// Every captured fixture, oldest first. Written by tests/live/capture.py.\n'
        + ''.join(f"import {{ FIXTURE as {i} }} from './{f.name}'\n" for i, f in zip(idents, files))
        + f'\nexport const FIXTURES = [{", ".join(idents)}]\n'
        + 'export const LATEST = FIXTURES[FIXTURES.length - 1]\n')
    print(f'wrote {FIXTURES / name} ({len(body)} bytes) and index.ts; review the diff before committing')


if __name__ == '__main__':
    main()
