#!/usr/bin/env python3
"""Manage only our private user-level Codex metrics block; never print its token."""
import argparse
import json
import os
from pathlib import Path
import re
import tempfile
import tomllib
from urllib.parse import urlsplit

BEGIN = "# BEGIN computerConfiguration: Codex metrics"
END = "# END computerConfiguration: Codex metrics"


def unmanaged(text):
    if BEGIN not in text and END not in text:
        return text
    pattern = rf"(?m)^{re.escape(BEGIN)}\n.*?^{re.escape(END)}(?:\n|$)"
    result, count = re.subn(pattern, "", text, flags=re.DOTALL)
    if count != 1 or BEGIN in result or END in result:
        raise ValueError("invalid Codex metrics block markers; review config.toml")
    return result


def configure(path, token_paths, endpoint, machine, check=False):
    path = Path(path)
    if path.is_symlink():
        raise ValueError("Codex config is a symlink; review it before enabling metrics")
    original = path.read_text() if path.exists() else ""
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
    # Validate the complete replacement before touching the original.
    tomllib.loads(desired)
    private = path.exists() and not reason and (path.stat().st_mode & 0o777) != 0o600
    changed = desired != original or private
    if changed and not check:
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=".config.toml-", dir=path.parent)
        try:
            with os.fdopen(fd, "w") as stream:
                stream.write(desired)
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
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
