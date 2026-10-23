#!/usr/bin/env python3
"""Reuse a live cached access token; never refresh or change OAuth credentials."""
import json
from pathlib import Path
import time


def headers(home):
    try:
        config = json.loads((home / '.claude.json').read_text())['mcpServers']['vkworkspace-assistant']
        credentials = json.loads((home / '.claude/.credentials.json').read_text()).get('mcpOAuth', {})
        for value in credentials.values():
            if value.get('serverName') != 'vkworkspace-assistant' or value.get('serverUrl') != config['url']:
                continue
            token, expiry = value.get('accessToken'), value.get('expiresAt', 0)
            if isinstance(expiry, (int, float)) and expiry > 1e11:
                expiry /= 1000
            if isinstance(token, str) and token and isinstance(expiry, (int, float)) and expiry > time.time() + 30:
                return {'Authorization': 'Bearer ' + token}
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        pass
    # Codex may fall back to its own stored OAuth credentials/login.
    return {}


if __name__ == '__main__':
    print(json.dumps(headers(Path.home())))
