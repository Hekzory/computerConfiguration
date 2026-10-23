"""Lossless, validated and atomic updates to private Codex configuration."""
import copy
import os
from pathlib import Path
import tempfile
import tomllib

import tomlkit


def delete_path(document, path):
    """Delete one owned key and empty parent tables, preserving other values."""
    current = document
    parents = []
    for key in path[:-1]:
        if key not in current:
            return
        parents.append((current, key))
        current = current[key]
        if not isinstance(current, dict):
            raise ValueError("owned path crosses a non-table value")
    current.pop(path[-1], None)
    for parent, key in reversed(parents):
        if parent[key]:
            break
        del parent[key]


def merge(document, updates):
    for key, value in updates.items():
        if isinstance(value, dict):
            if key not in document:
                document[key] = tomlkit.table()
            if not isinstance(document[key], dict):
                raise ValueError("owned path crosses a non-table value")
            merge(document[key], value)
        else:
            document[key] = value


def read_config(path):
    path = Path(path)
    if path.is_symlink():
        raise ValueError("Codex config is a symlink; review it before editing")
    return path.read_text() if path.exists() else ""


def write_config(path, original, desired, check=False, private=True):
    """Refuse stale snapshots and validate before atomic, private replacement."""
    path = Path(path)
    tomllib.loads(desired)
    changed = desired != original or (private and path.exists() and (path.stat().st_mode & 0o777) != 0o600)
    if changed and not check:
        if read_config(path) != original:
            raise ValueError("Codex configuration changed during update; retry")
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=".config.toml-", dir=path.parent)
        try:
            with os.fdopen(fd, "w") as stream:
                stream.write(desired)
            if read_config(path) != original:
                raise ValueError("Codex configuration changed during update; retry")
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
    return changed


def configure(path, updates, removals=(), check=False):
    original = read_config(path)
    expected = copy.deepcopy(tomllib.loads(original))
    document = tomlkit.parse(original)
    for owned_path in removals:
        if not owned_path or not all(isinstance(key, str) for key in owned_path):
            raise ValueError("invalid owned path")
        delete_path(document, owned_path)
        delete_path(expected, owned_path)
    merge(document, updates)
    # Independent plain-value merge verifies that no unrelated values changed.
    def plain_merge(target, values):
        for key, value in values.items():
            if isinstance(value, dict):
                plain_merge(target.setdefault(key, {}), value)
            else:
                target[key] = value
    plain_merge(expected, updates)
    desired = tomlkit.dumps(document)
    if tomllib.loads(desired) != expected:
        raise ValueError("unexpected configuration change")
    return write_config(path, original, desired, check)
