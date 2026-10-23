#!/usr/bin/env python3
"""Add the two selected corporate handlers without replacing personal hooks."""
import argparse
import json
import os
from pathlib import Path
import shlex
import tempfile


def configure(path, home, check=False):
    path, home = Path(path), Path(home)
    if path.is_symlink():
        raise ValueError('hooks config is a symlink')
    original = path.read_text() if path.exists() else ''
    config = json.loads(original) if original else {}
    hooks = config.setdefault('hooks', {})
    changed = False
    for event, matcher, command, timeout in (
        ('PreToolUse', '^Bash$', '/usr/bin/python3 ' + shlex.quote(str(home / '.codex/hooks/mcc-guard.py')), 10),
        ('SessionStart', None, '/usr/bin/python3 ' + shlex.quote(str(home / '.local/share/agent-context/work-context.py')), 5),
    ):
        groups = hooks.setdefault(event, [])
        if any(h.get('command') == command for group in groups for h in group.get('hooks', [])):
            continue
        group = {'hooks': [{'type': 'command', 'command': command, 'timeout': timeout}]}
        if matcher:
            group['matcher'] = matcher
        groups.append(group)
        changed = True
    if changed and not check:
        desired = json.dumps(config, ensure_ascii=False, indent=2) + '\n'
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix='.hooks-', dir=path.parent)
        try:
            with os.fdopen(fd, 'w') as stream:
                stream.write(desired)
            if path.is_symlink() or (path.read_text() if path.exists() else '') != original:
                raise ValueError('hooks config changed during update')
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
    return changed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', required=True)
    parser.add_argument('--home', required=True)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    try:
        changed = configure(args.config, args.home, args.check)
    except (OSError, ValueError, TypeError, AttributeError):
        parser.exit(1, 'Codex corporate hooks: invalid configuration; no change applied.\n')
    print('updated' if changed else 'unchanged')


if __name__ == '__main__':
    main()
