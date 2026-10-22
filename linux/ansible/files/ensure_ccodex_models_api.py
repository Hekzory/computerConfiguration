#!/usr/bin/env python3
"""Fill in Codex's model discovery URL without resetting the user's router config."""
import json
import os
from pathlib import Path
import stat
import sys
import tempfile

MODELS_API_URL = 'https://chatgpt.com/backend-api/codex/models'


def ensure_models_api_url(path):
    config = json.loads(path.read_text(encoding='utf-8'))
    providers = config.get('Providers')
    if not isinstance(providers, list):
        raise ValueError('Router configuration has no Providers list')
    codex = [item for item in providers if isinstance(item, dict) and item.get('name') == 'codex']
    if len(codex) > 1:
        raise ValueError('Router configuration has multiple codex providers')
    if not codex or 'models_api_url' in codex[0]:
        return False

    codex[0]['models_api_url'] = MODELS_API_URL
    original_mode = stat.S_IMODE(path.stat().st_mode)
    fd, temp_name = tempfile.mkstemp(prefix='.config.', suffix='.json', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as output:
            os.fchmod(output.fileno(), original_mode)
            json.dump(config, output, indent=2, ensure_ascii=False)
            output.write('\n')
            output.flush()
            os.fsync(output.fileno())
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)
    return True


def main():
    if len(sys.argv) != 2:
        sys.exit('Usage: ensure_ccodex_models_api.py CONFIG_PATH')
    try:
        changed = ensure_models_api_url(Path(sys.argv[1]))
    except (OSError, ValueError, TypeError) as error:
        sys.exit(f'Cannot update ccodex model URL: {type(error).__name__}')
    print('updated' if changed else 'unchanged')


if __name__ == '__main__':
    main()
