# Model completion reads the local router config; it never starts the router.
function __fish_ccodex_models
    python3 -c '
import json
from pathlib import Path
models = ["gpt-6.1-sol", "gpt-6-astra", "gpt-6-luna"]
try:
    config = json.loads((Path.home() / ".claude-code-router/config.json").read_text())
    provider = next(item for item in config.get("Providers", []) if item.get("name") == "codex")
    discovered = provider.get("models")
    if isinstance(discovered, list):
        models = [model for model in discovered if isinstance(model, str)]
except (OSError, ValueError, TypeError, AttributeError, StopIteration):
    pass
for model in dict.fromkeys(models):
    print(model + "\tCodex model")
'
end

complete -c ccodex -f
set -l available 'not __fish_seen_argument -l setup -l auth -l restart -l status -l help -s h'
complete -c ccodex -n "$available" -l setup -d 'Fresh OAuth login and model discovery'
complete -c ccodex -n "$available" -l auth -d 'Fresh OAuth login without discovery'
complete -c ccodex -n "$available" -l doctor -d 'Send a small subscription test request'
complete -c ccodex -n "$available" -l restart -d 'Restart the router when idle'
complete -c ccodex -n "$available" -l status -d 'Show router status without starting it'
complete -c ccodex -n "$available" -s h -l help -d 'Show help'
complete -c ccodex -n "$available" -l model -x -a '(__fish_ccodex_models)' -d 'Select a Codex model'
complete -c ccodex -n "$available" -s c -l continue -d 'Continue the most recent conversation'
complete -c ccodex -n "$available" -s r -l resume -d 'Resume a conversation'
complete -c ccodex -n "$available" -s p -l print -d 'Print the response and exit'
complete -c ccodex -n "$available" -s n -l name -x -d 'Set the session name'
complete -c ccodex -n "$available" -l effort -x -a 'low medium high xhigh max' -d 'Set reasoning effort'
complete -c ccodex -n "$available" -l permission-mode -x -a 'acceptEdits auto bypassPermissions manual dontAsk plan' -d 'Set permission mode'
complete -c ccodex -n "$available" -l output-format -x -a 'text json stream-json' -d 'Set print output format'
complete -c ccodex -n "$available" -l input-format -x -a 'text stream-json' -d 'Set print input format'
complete -c ccodex -n "$available" -l add-dir -r -a '(__fish_complete_directories)' -d 'Allow access to another directory'
complete -c ccodex -n "$available" -l settings -r -F -d 'Load additional settings'
complete -c ccodex -n "$available" -l mcp-config -r -F -d 'Load MCP server configuration'
complete -c ccodex -n "$available" -l debug-file -r -F -d 'Write debug logs to a file'
complete -c ccodex -n "$available" -l verbose -d 'Enable verbose output'
complete -c ccodex -n "$available" -s v -l version -d 'Show Claude Code version'
