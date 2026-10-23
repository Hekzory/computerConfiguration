#!/usr/bin/env python3
"""Manage only our private user-level Codex metrics block; never print its token."""
import argparse
import json
import copy
from pathlib import Path
import re
import tomllib
from urllib.parse import urlsplit

import tomlkit

from config_edit import delete_path, read_config, write_config

BEGIN = "# BEGIN computerConfiguration: Codex metrics"
END = "# END computerConfiguration: Codex metrics"
OWNED = [
    ("otel", key) for key in ("environment", "exporter", "trace_exporter", "log_user_prompt")
] + [
    ("otel", "metrics_exporter", "otlp-http", key) for key in ("endpoint", "protocol")
] + [("otel", "metrics_exporter", "otlp-http", "headers", "Authorization")]
COMMENT = "# Metrics only. env identifies the machine, including a -wsl suffix under WSL.\n"


def unmanaged(text):
    if BEGIN not in text and END not in text:
        return text
    pattern = rf"(?m)^{re.escape(BEGIN)}\n(.*?)^{re.escape(END)}(?:\n|$)"
    matches = list(re.finditer(pattern, text, flags=re.DOTALL))
    if len(matches) != 1 or text.count(BEGIN) != 1 or text.count(END) != 1:
        raise ValueError("invalid Codex metrics block markers; review config.toml")
    match = matches[0]
    # Desktop writes may place unrelated tables before END. Markers delimit a
    # search area, not permission to delete its contents. Own only these leaves.
    original_body = match.group(1).replace(COMMENT, "", 1)
    body = tomlkit.parse(original_body)
    expected = copy.deepcopy(tomllib.loads(text))
    for path in OWNED:
        # Only delete keys actually present in this managed region.
        current = body
        for key in path:
            if not isinstance(current, dict) or key not in current:
                break
            current = current[key]
        else:
            delete_path(body, path)
            delete_path(expected, path)
    retained = tomlkit.dumps(body)
    # TOML associates comments before a foreign header with the preceding
    # metrics table. Keep those comments when pruning an empty managed table.
    comments = re.findall(r"(?m)^[ \t]*#[^\n]*(?:\n|$)", original_body)
    retained = ''.join(line for line in comments if line not in retained) + retained
    result = text[:match.start()] + retained + text[match.end():]
    if tomllib.loads(result) != expected:
        raise ValueError("unexpected change outside managed metrics keys")
    return result


def configure(path, token_paths, endpoint, machine, check=False):
    path = Path(path)
    original = read_config(path)
    base = unmanaged(original)
    config = tomllib.loads(base)
    reason = ""
    if "otel" in config or any("otel" in p for p in config.get("profiles", {}).values()):
        reason = "existing telemetry configuration"
    elif config.get("analytics", {}).get("enabled") is False:
        # CLI 0.163 disables custom exporters too. Respect the user's opt-out.
        reason = "analytics disabled"
    else:
        token_path = next((Path(p) for p in token_paths if Path(p).is_file()), None)
        if token_path is None:
            reason = "no ingest token"

    desired = base
    if not reason:
        token = token_path.read_text().strip()
        if not token or any(ord(c) < 33 or ord(c) > 126 for c in token):
            raise ValueError("ingest token must be one nonempty printable ASCII value")
        url = urlsplit(endpoint)
        if url.scheme != "https" or not url.hostname or url.username or url.password:
            raise ValueError("metrics endpoint must use HTTPS without URL credentials")
        if not machine:
            raise ValueError("a machine name is required")
        quote = lambda value: json.dumps(value, ensure_ascii=False)
        block = f'''{BEGIN}
# Metrics only. env identifies the machine, including a -wsl suffix under WSL.
[otel]
environment = {quote(machine)}
exporter = "none"
trace_exporter = "none"
log_user_prompt = false

[otel.metrics_exporter.otlp-http]
endpoint = {quote(endpoint)}
protocol = "binary"

[otel.metrics_exporter.otlp-http.headers]
Authorization = {quote("Bearer " + token)}
{END}
'''
        desired = base + ("\n" if base and not base.endswith("\n") else "") + block
    changed = write_config(path, original, desired, check, private=not reason)
    return changed, reason


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True)
    parser.add_argument("--token", action="append", default=[])
    parser.add_argument("--endpoint", required=True)
    parser.add_argument("--machine", required=True)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    try:
        changed, reason = configure(args.config, args.token, args.endpoint, args.machine, args.check)
    except (OSError, ValueError):
        # TOML errors can include secret values. Keep diagnostics deliberately generic.
        parser.exit(1, "Codex metrics: invalid configuration or unreadable token; no change applied.\n")
    print(("updated" if changed else "unchanged") + (": " + reason if reason else ""))


if __name__ == "__main__":
    main()
