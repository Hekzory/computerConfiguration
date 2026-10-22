#!/usr/bin/env python3
"""Keep Codex model discovery and the three GPT-6 tiers configured safely."""
import json
import os
from pathlib import Path
import stat
import sys
import tempfile

MODELS_API_URL = 'https://chatgpt.com/backend-api/codex/models'
MODEL_IDS = ('gpt-6.1-sol', 'gpt-6-astra', 'gpt-6-luna')


def ensure_models_api_url(path):
    config = json.loads(path.read_text(encoding='utf-8'))
    providers = config.get('Providers')
    if not isinstance(providers, list):
        raise ValueError('Router configuration has no Providers list')
    codex = [item for item in providers if isinstance(item, dict) and item.get('name') == 'codex']
    if len(codex) > 1:
        raise ValueError('Router configuration has multiple codex providers')
    if not codex:
        return False

    provider = codex[0]
    changed = False
    if 'models_api_url' not in provider:
        provider['models_api_url'] = MODELS_API_URL
        changed = True

    if 'models' not in provider:
        provider['models'] = []
    models = provider['models']
    if not isinstance(models, list) or not all(isinstance(model, str) for model in models):
        raise ValueError('Codex provider models must be a list of strings')
    for model in MODEL_IDS:
        if model not in models:
            models.append(model)
            changed = True
    if not changed:
        return False
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
        sys.exit(f'Cannot update ccodex model configuration: {type(error).__name__}')
    print('updated' if changed else 'unchanged')


if __name__ == '__main__':
    main()
