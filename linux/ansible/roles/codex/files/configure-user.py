#!/usr/bin/env python3
"""Merge selected Codex policy keys without replacing app-owned configuration."""
import argparse
import json

from config_edit import configure


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', required=True)
    parser.add_argument('--updates-json', default='{}')
    parser.add_argument('--remove-json', default='[]')
    parser.add_argument('--disabled-skills-json', default='[]')
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    try:
        updates = json.loads(args.updates_json)
        removals = json.loads(args.remove_json)
        disabled_skills = json.loads(args.disabled_skills_json)
        if (not isinstance(updates, dict) or not isinstance(removals, list)
                or not isinstance(disabled_skills, list)
                or not all(isinstance(name, str) and name.strip() for name in disabled_skills)):
            raise ValueError('invalid policy')
        changed = configure(args.config, updates, removals, args.check,
                            disabled_skills=disabled_skills)
    except (OSError, ValueError, TypeError, KeyError):
        parser.exit(1, 'Codex policy: invalid configuration; no change applied.\n')
    print('updated' if changed else 'unchanged')


if __name__ == '__main__':
    main()
