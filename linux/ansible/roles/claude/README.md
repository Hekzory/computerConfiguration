# Optional Claude Code setup

From `linux/ansible/`:

```bash
./run.sh arch-core --claude
./run.sh arch-desktop --claude
./run.sh arch-home --corporate --claude
```

The role installs the `claude-code` package and ccodex, deploys its own user
helpers/completions, and manages the Claude-only policies, telemetry and mods.
All three normal playbooks reach it through arch-core. `--corporate` is a
separate opt-in; either flag can be used alone or both in either order.

Without `--claude`, none of these tasks run, including cleanup tasks. Existing
installations, policy and credentials are preserved. This is a provisioning
switch, not an uninstaller or a runtime switch for an installed client.
`~/.claude/settings.json`, OAuth credentials and tokens are never deployed.

The shared SSH-to-fish guard remains at `../../files/ssh-fish-guard.py`, used
independently by native Codex. Its Claude copy is deployed only by this role.

## Configuration
Split in two on purpose: the helper scripts are dotfiles under `roles/claude/files/user_home/.claude/`, the settings that point at them are a *policy* drop-in at `/etc/claude-code/managed-settings.d/10-claude-personal.json` (rendered from `roles/claude/templates/`).

`~/.claude/settings.json` is never touched — it holds API tokens and proxy env on work machines and must stay out of git. Policy settings outrank user and project ones, so `attribution` (empty = no Co-Authored-By, no PR trailer, no session link) can't be flipped by a per-repo settings file. Same for `promptSuggestionEnabled` and `awaySummaryEnabled` (both `false`): every suggestion and recap is a hidden main-model request over the whole context. The same drop-in sets `CLAUDE_CODE_SHELL=/usr/bin/bash` (otherwise Claude Code picks zsh, whose globbing and `=word` rules break the bash the model writes) and wires two PreToolUse hooks: `git-guard.sh` (no AI attribution in commits) and `ssh-fish-guard.py` (bash syntax sent to a remote fish login shell gets `bash -s` instead). Model and effort deliberately stay out of the policy file so `/model` and `/effort` keep working.

Usage metrics are a second drop-in, `20-claude-telemetry.json`: OTLP metrics (no logs, no traces) to `https://otel.tsv.one/v1/metrics`, which lands in VictoriaMetrics on o-srv and the "Claude Code" dashboard on grafana.tsv.one, one instance per `host.name` (`claude_otel_host`: the hostname, `-wsl` appended under WSL). It is opt-in per machine: the drop-in ships only where `~/.claude/otel-token` exists, and is removed everywhere else. The token never enters git or `/etc` — `otel-headers.sh` (the `otelHeadersHelper`) reads it at runtime, so it also stays out of the env every Claude command inherits. The playbook also leaves telemetry off when any managed or user settings file already mentions `OTEL_`/telemetry: a later drop-in overrides an employer policy key by key and would silently steal the employer's telemetry. Server side (token check, the store, the dashboard) lives in the private nginx-gateway and monitoring repos.

To turn metrics on for a machine (`<o-srv>` = the home server, kept out of this public repo):
```fish
ssh <o-srv> make -sC nginx-gateway otel-token | install -m600 /dev/stdin ~/.claude/otel-token
./run.sh arch-core --claude
```
Running sessions keep their old settings; new ones export. Delete the token file and rerun to turn it off.

The spend meter (github.com/Hekzory/spend-meter, a pane with the session's cost) is a third drop-in, `30-claude-spend-meter.json`: it declares the plugin's GitHub marketplace with `autoUpdate: true` and enables the plugin, so every machine installs it and picks up each release on startup (Claude Code auto-updates only Anthropic's own marketplaces by default). It is left out, and removed, on a machine that runs the mod from a working copy (a folder marketplace named `spend-meter` in `~/.claude/settings.json`), which policy would otherwise switch to GitHub, and on one whose policy sets `strictKnownMarketplaces`. Drop-ins deep-merge, so its `extraKnownMarketplaces` entry adds to an employer's rather than replacing them.

lean-harness (`roles/claude/files/mods/plugins/lean-harness`) trims what every request re-reads; together with the skill overrides and the Docs deny below that is about 9.6k tokens of a 44k prefix. It moves three rarely used tools behind ToolSearch (ScheduleWakeup, SendFeedback, ReportFindings) and names them in one prompt line. It drops product blurbs, the idle `<total_tokens>` line and its per-request reminder, and Fable's identity blurb. It hides the `statusline-setup` agent, since policy owns the status line. It only touches what ships with Claude Code: an agent, MCP server or plugin added on the machine passes through untouched, even under a trimmed name. The skill listing is trimmed by policy, not by the mod: `skillOverrides` in `10-claude-personal.json` keeps built-ins you start yourself out of the model's view (they still run as `/name`), lists claude.ai's file-format and research skills by name only and turns off the ones these machines can't use. It is keyed by bare name, so a personal or project skill must not reuse one of those names (plugin skills are namespaced and unaffected), and `/skills` shows them as set by policy. Only a plugin policy seats may rewrite the prompt (on a machine with managed settings the built-in sec-default skips the prompt hooks of anything a user installs), so the playbook copies the mod to `/etc/claude-code/mods` (a folder marketplace, root-owned) and a fourth drop-in, `40-claude-lean-harness.json`, seats it with `prependPlugins`. That list replaces Claude Code's default, so it names `sec-default@builtin` again, and the drop-in is left out where another policy sets the tier lists or allowlists marketplaces. The Claude Docs connector is denied by name in `10-claude-personal.json`; Claude Code joins `deniedMcpServers` from every policy source, and a connector added on claude.ai later still loads.

CI only runs lightweight static checks and offline ccodex tests when this role changes. It does not install Claude Code, run against npm's latest release, or run weekly. The captured fixture tests and live stand-in API checks remain in `files/mods/plugins/lean-harness/tests` for manual use with a compatible Claude Code installation. They are not a promise of compatibility with each new Claude release.

`--claude` also installs `ccodex` (`roles/claude/files/ccodex`): Claude Code through [cco-router](https://github.com/Hekzory/cco-router) with ChatGPT subscription OAuth; the npm package is still named `@caeliq/claude-code-router`. The playbook installs a pinned GitHub Release `.tgz`, verifies its SHA-256 and skips npm when that version is already installed; no GitHub token or install scripts are needed. Releases are built and tested in cco-router, never edited in `node_modules`. After an update, `ccodex --restart` loads the new code once the router is idle. The npm package lives in `~/.local/share/ccodex/router`; `files/ccodex-router.json` seeds `~/.claude-code-router/config.json` with `force: false`, since discovery edits it and local providers may contain keys. `files/ensure_ccodex_models_api.py` adds the missing Codex `models_api_url` and the three GPT-6 tiers (Astra, 6.1 Sol, Luna) to existing installs, preserving a custom URL, credentials, discovered models and other provider settings; don't replace the entire config or deploy OAuth tokens. `ccodex --setup` always forces a new browser login and model discovery (it must not trust an existing `codex_auth.json` after the refresh token is invalidated); `ccodex --auth` forces login without discovery. Both verify that the auth file changed. The router automatically refreshes ordinary expired access tokens with its own locked refresh flow; a server-invalidated refresh token needs interactive login, not another refresh timer. The router starts on demand on loopback port 1455. Endpoint/model overrides and `disableClaudeAiConnectors: true` are per-launch, not policy or user settings, so plain `claude` and local MCP servers are unchanged. `--status` reports the live process, Node and active requests without starting a router or sending inference. `--restart` verifies the process UID, CLI path and start time through `/proc`, refuses active requests or another installation, then waits for the listener to close before starting its own router; it never escalates to SIGKILL. Fish completions ship as a dotfile, read model IDs from the local config and work before login, without network calls. Tests: `timeout 30s python3 -m unittest discover -s roles/claude/tests -p 'test_ccodex.py'` from `linux/ansible/` (no network or account).

Skills and MCP config are not shipped: the ones on the work laptop are all corporate. This repo is public — keep it that way.

## ccodex

`--claude` also installs `ccodex`: Claude Code through the [cco-router](https://github.com/Hekzory/cco-router), using a ChatGPT subscription rather than an OpenAI API key. The package is pinned to a GitHub Release archive with SHA-256 verification; downloading it needs no token. After applying the playbook:

```bash
ccodex --setup          # fresh browser OAuth login, then model discovery
ccodex                 # same arguments as claude
ccodex --doctor        # small inference check; uses subscription quota
ccodex --status        # process, Node version and active requests; no inference
ccodex --restart       # restart this installation's router when idle
ccodex --model gpt-6-astra  # flagship; or gpt-6.1-sol (default), gpt-6-luna
                         # CCODEX_MODEL also selects the model
```

Plain `claude` and `~/.claude/settings.json` stay unchanged. claude.ai connectors are disabled for `ccodex`; local MCP servers still load. The router listens on `127.0.0.1:1455` for OAuth callbacks and starts on demand. `~/.claude-code-router/config.json` is seeded only when absent; `arch-core` adds the Codex `models_api_url` if missing and adds GPT-6 Astra, GPT-6.1 Sol and GPT-6 Luna to existing configs without removing discovered models, credentials or custom endpoints. All other local edits survive playbook runs. OAuth tokens stay alongside it, outside git. CCR automatically refreshes access tokens before expiry and coordinates concurrent refreshes; `ccodex` does not make a second refresh attempt. If OpenAI invalidates the refresh token (`refresh_token_invalidated`), automated renewal cannot recover it: run `ccodex --setup` to force a fresh browser login and rediscover models, or `ccodex --auth` to log in without discovery. Both verify the saved auth file actually changed before reporting success. These are configured model IDs, not a promise that the subscription exposes all three; verify access with `ccodex --doctor --model MODEL`.

Fish completions include wrapper options, common Claude Code arguments and models from the local router config. They work before OAuth setup and make no network requests. `--status` leaves a stopped router stopped; `--restart` checks the live process identity, refuses active requests or another installation, and waits for the port to close before starting a replacement.

## Checks

CI is limited to role changes (or a manual dispatch): shell, JavaScript, Python
and JSON checks plus the offline router tests. For a local offline check:

```bash
python3 -m unittest discover -s roles/claude/tests -p 'test_*.py' -v
```

Fixture and live Claude mod tests remain available under
`files/mods/plugins/lean-harness/tests`; they require a compatible Claude CLI
and are no longer part of the default or scheduled CI. Installing or updating
Claude through `--claude` does not imply these mods support every new release.
