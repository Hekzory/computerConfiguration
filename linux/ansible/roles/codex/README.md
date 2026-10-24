# Native Codex configuration

`arch-core` imports this role, including when used by the desktop/home playbooks
or under WSL. Apply from `linux/ansible/` with the usual `./run.sh arch-core`.
This configures Codex; it does not install the CLI or log in for you.

The role deploys root-owned `/etc/codex/config.toml` and three scripts under
`/etc/codex/hooks/`. It enables lifecycle hooks and the native footer's model with
reasoning level, used context percentage, context window size and current directory.
The main model remains a user choice. Main and planning reasoning default to
`high`; higher-precedence user settings such as `xhigh` still win.

Commands use `workspace-write` sandboxing with network access enabled. Approvals
stay `on-request` and go to the user. Downloads and API calls can run inside the
sandbox; writes outside the workspace and protected paths such as `.git/` still
need approval. Network access includes uploads and local/private destinations,
and the sandbox does not add credential read restrictions. These are defaults
for new sessions, subject to higher-precedence settings and managed requirements.
See [sandbox and approvals](https://learn.chatgpt.com/docs/agent-approvals-security).

The role also installs `~/.codex/rules/claude-import.rules`, selected global
command approvals: Go build/test/vet/version, npm's build/check/lint/
type-check/unit scripts, `uv run pytest`, bounded journal reads, selected `ip`
show/get commands, `resolvectl status`, `getent hosts`, `systemctl --user status/cat`,
`nvim --version`, `tree-sitter --version`, `/bin/ls`, `pnpm build`,
`pnpm run build/check`, `bun run build/check` and `python3 -m unittest`.
Git approvals cover staging with `git add --`, `git add -A --` and
`git add -u --`; status, ls-files, ls-tree, rev-parse, rev-list and describe;
`git worktree list`, `git remote get-url` and `git pull --ff-only`.
GitHub CLI approvals cover PR view/list/diff/checks, run view/list, repo view
and release view/list. GitLab CLI approvals cover MR view/list/diff.
Matching commands may run outside the sandbox without prompting in any project
for this user.
Rules match argument prefixes, so extra arguments are permitted too. Inline
`match` and `not_match` examples are checked by Codex when the file loads.
Build/test approvals execute repository-defined code in any repository.
Staging can execute configured Git clean filters. The pull prefix prefers
fast-forward updates but does not enforce them: trailing options can override
`--ff-only`, and explicit refspecs can update other local refs. Plain `git pull`,
`git fetch`, reset/clean and publication commands have no allow rule.
Both agents receive instructions to use finite journal output limits; prefix
rules match the shown argument order and permit additional trailing arguments.
PowerShell, curl and headless Neovim approvals were deliberately excluded.
Restart Codex after changing rules. See [command rules](https://learn.chatgpt.com/docs/agent-configuration/rules).

`project_doc_fallback_filenames = ["CLAUDE.md", "claude.md"]` reuses existing
project guidance. In each directory, `AGENTS.override.md` and `AGENTS.md` take
precedence; Codex reads the first non-empty matching file, not both agents' files.
The normal root-to-working-directory discovery and instruction size limit apply.
See [instruction discovery](https://learn.chatgpt.com/docs/agent-configuration/agents-md).

On Linux, Codex falls back to Bash for a fish login account; fish isn't one of
its supported execution shells. `allow_login_shell = false` keeps commands out
of login profiles (including profiles that start fish). Shell snapshots and
experimental profile loading are disabled too, and `BASH_ENV=/dev/null` prevents
non-interactive Bash from sourcing a separately configured startup script.
Child programs see `SHELL=/usr/bin/bash`; this environment variable doesn't
select Codex's own interpreter. A machine with a supported login shell such as
zsh still needs an explicit Bash selection in the shell tool. This Linux role
doesn't change native Windows execution from PowerShell to Bash.

Agent commands inherit the usual environment, with pagers disabled for ordinary
tools, Git, systemd and man. `GIT_TERMINAL_PROMPT=0` makes missing Git credentials
fail instead of waiting for terminal input. Inherited `PATH` must already expose
the tools you need; new sessions no longer recover paths from login scripts.
See [shell settings](https://learn.chatgpt.com/docs/config-file/config-reference).

The shared fish and PowerShell configs recognize `CODEX_THREAD_ID` and `CODEX_CI`
alongside `CLAUDECODE` and `CURSOR_TRACE_ID`. Even an interactive agent shell skips
banners and theme initialization, disables pagers and avoids Git credential
prompts. Fish also skips its theme download and interactive aliases, and removes
the destructive Git wrappers that wait for confirmation. Human terminals retain
their usual startup and confirmations.

The commit guard applies the existing no-attribution policy to Codex as well:
Co-Authored-By, generated-with/by/using Claude/Codex/OpenAI/ChatGPT, AI noreply
addresses and the robot emoji are rejected in explicit `git commit` command text.
The denial asks the agent to retry without attribution. Ordinary messages about
Codex or the OpenAI API are allowed. As with the existing Claude guard, this is a
workflow check, not a security boundary: file-sourced messages, Git aliases and
arbitrary scripts aren't inspected. It doesn't modify Git's global hook settings.

The SSH-to-fish guard is copied unchanged from
`user_home/.claude/hooks/ssh-fish-guard.py`. Its deployed copy is independent of
Claude; both clients retain the same behavior and one source of truth.

Claude Code, ccodex, their configuration, plugins and credentials stay untouched.
So do auth files, user/project hooks, MCP servers and
`requirements.toml`. The system config is a defaults layer, not a replacement for
user settings: a higher-precedence footer choice still wins, and explicitly
turning off `features.hooks` at a higher layer disables hooks. System hooks are
managed/trusted by Codex; no hook-trust bypass is used.

A pre-existing `/etc/codex/config.toml` without this role's ownership marker (or a
symlink) stops deployment before writing anything. Review existing system settings
before adopting the role; it will not silently overwrite an employer's config.
Later runs update the managed files idempotently. Hook scripts are installed
before the configuration, whose TOML is validated before replacement.

Start a new Codex session after deployment and inspect `/hooks` for the handlers.
Use a recent CLI with `PreToolUse` support. A hook error/timeout is not a guaranteed
denial, so these checks must not be mistaken for a sandbox.

## Desktop browser connection

Before `mcp__cua_repl__js`, a synchronous hook checks whether the current chat has
an in-app browser connection in ChatGPT Desktop. A chat created in the CLI may
have the browser plugin available while Desktop has no window registered for
that chat. The hook opens `codex://threads/<session_id>` in Desktop when needed
and waits up to 20 seconds for a matching `getInfo` response. This may launch or
focus Desktop and switch it to the current chat; it does not start a model turn.

Desktop must already be installed and exposed as `chatgpt` or `codex-desktop` on
`PATH`; the role does not install it. Without either executable, the hook exits
immediately without probing sockets or writing cache files. Invalid input,
launch/connection errors, timeouts and unexpected helper errors also fail open:
the hook returns no approval, denial or rewritten tool input, leaving the
original browser call and normal permission checks to proceed.

The helper only probes owned sockets under `/tmp/codex-browser-use` and accepts
an `iab` backend whose metadata matches the current session. A per-session lock
prevents duplicate launches from parallel calls. Its cache under
`${XDG_CACHE_HOME:-~/.cache}/codex-browser-hook` is revalidated on every call so
Desktop restarts do not leave a stale successful marker. The socket handshake
is an internal Desktop protocol; incompatible versions fail open.

## Configuration ownership

| Owner | Files or keys |
| --- | --- |
| Base role | `/etc/codex/config.toml`, system hooks/editors, marked working agreements and `claude-import.rules` |
| Selected user policy | Leaves in `codex_user_config_updates`, paths in `codex_user_config_remove`, and names in `codex_user_disabled_skills` |
| Metrics helper | Marked `otel.environment`, exporter/trace exporter, prompt logging, HTTP metrics endpoint/protocol and its Authorization header |
| Optional corporate role | Its three corporate MCP policies, adapters, skill links, research role and selected hook handlers |
| Desktop / account | Plugin switches, marketplaces, generated `node_repl` paths/environment, OAuth, onboarding, hook trust hashes, appearance and queue/detail preferences |
| User | All other configuration, credentials and private work context |

`codex_user_config_updates` recursively merges selected leaves; it never replaces
the whole document. Removals use lists of path components, preserving quoted or
hyphenated names. Values are parsed and checked before an atomic private write.
No credentials belong in these variables or in Git. Helpers support `--check`
without writes; Ansible calls them in check mode only if the installed editor is
available. On a fresh host the install tasks report planned changes, and user
configuration validation requires a subsequent check after installation.

Do not restore missing plugin/runtime tables from old snapshots. Their ownership
stays with the desktop; inspect effective availability in a fresh supported
session. The role preserves late search, summary, theme, memory and trust choices.

The default removal list deletes only `features.analytics_plan_history`. It does
not disable `analytics.enabled` or the private metrics exporter. A later role run
reconciles this deprecated flag if a client writes it again.
The default updates disable ambient suggestions, the Work Pets, Pages, bundled
LaTeX and Code Review plugins, and the Hotline, Pets, Pages and Safety Settings
apps. The Codex App Tools server also excludes voice-call termination, chat
sharing and its two LaTeX tools while retaining the other app tools.
The server is disabled by default so standalone CLI sessions do not start it
without `CODEX_APP_TOOLS_PIPE_PATH`. The desktop app supplies a session override
to enable the server when its app-tools pipe is available.
`codex_user_disabled_skills` also disables the three `work-pets:*` and four
`pages:*` skills by name, independent of cached plugin versions. Other skill
rules are preserved; the managed name rules follow existing path overrides.
Override the policy variables to change these selections.

## Metrics

The role enables native Codex OTLP/HTTP metrics when `~/.codex/otel-token` exists,
falling back to the existing personal `~/.claude/otel-token`. Obtain the ingest
token with `make otel-token` in nginx-gateway on o-srv. Tokens stay outside Git.
With neither token available, this exporter stays off and the role removes its
metrics block on the next run. An existing Codex `[otel]` configuration or an explicit
`analytics.enabled = false` keeps this role's exporter off.

Only the metrics keys inside a marked block in `~/.codex/config.toml` are managed;
foreign tables inserted by the desktop before its END marker are preserved when
the block is migrated. Unknown telemetry fields are retained and prevent adopting
the role's exporter. The role installs `python-tomlkit` for lossless TOML edits,
validates values independently with Python's `tomllib`, and rejects a file that
changes while an update is being prepared. The file is written atomically with
mode `0600` because the native
exporter needs a static Authorization header. The token is never put into shell
environment variables or command arguments. Logs, traces and prompt export are
disabled in this block. Project-local telemetry configuration is ignored by Codex.

Metrics go to `https://otel.tsv.one/v1/metrics`, through the existing authenticated
gateway into VictoriaMetrics on o-srv. No local collector or listening port is
needed. Override `codex_otel_endpoint`, `codex_otel_machine` or
`codex_otel_token_paths` in Ansible if needed. The native `otel.environment`
resource attribute (`env` in VictoriaMetrics) identifies the machine: hostname,
with `-wsl` appended under WSL. This works from desktop and CLI launches without
a shell wrapper. Do not reuse a machine label on two different machines.

The [Codex dashboard](https://grafana.tsv.one/d/codex/codex) is provisioned by
o-srv's monitoring repo, with Machine and Model filters. Codex 0.163 exports delta
counters and histograms; totals use `sum_over_time`, including histogram `_sum`
and `_count`, rather than `rate` or `increase`. Token types overlap: input includes
cached input, and output includes reasoning output. The dashboard totals use only
`token_type="total"`. Metrics flush periodically and at process shutdown; restart
Codex after applying the role. The running session does not reload its exporter.
Apply just the Codex role with `ansible-playbook arch-core.yml --tags codex` from
`linux/ansible/` after authenticating sudo, or use the usual full playbook run.

See the [official telemetry settings](https://learn.chatgpt.com/docs/config-file/config-reference)
and [metrics catalog](https://learn.chatgpt.com/docs/config-file/config-advanced#metrics).

## Shared memory and instructions

The system defaults enable local Codex memories with `gpt-6.1-sol` for extraction
and `gpt-6-astra` for consolidation. Built-in background memory jobs use their own
lower effort levels, an explicitly approved exception to the high-or-higher
instruction. User-level config can override these defaults, including either
memory model. These background requests use Codex quota.

The role manages a marked block in `~/.codex/AGENTS.md` from
[`files/AGENTS.md`](files/AGENTS.md), preserving personal instructions outside the
block. It contains the no-Luna rule, reasoning minimum and shared working
agreements. Start a new Codex session after deployment.

Memory contents stay on each machine under its Codex home; this repository does
not deploy memories or chat history. To bring over eligible Claude memories, use
Codex's local `/import` flow and select only memory items. In CLI 0.163.0, launch
with `codex --enable external_agent_memory_import` to expose memory imports for
that session. The importer needs reliable project scope and may skip projects
without session metadata. `/import` is unavailable during an active task or in a
remote or daemon-connected session.

Use `/memories` for chat-level controls. Turning off generation does not erase
existing memories. See the [memory documentation](https://learn.chatgpt.com/docs/customization/memories)
and [import guide](https://learn.chatgpt.com/docs/import).

## Tests

From `linux/ansible/`:

```sh
python3 -m unittest discover -s tests -p 'test_codex.py' -v
python3 -m unittest discover -s tests -p 'test_agent_shells.py' -v
python3 -m unittest discover -s tests -p 'test_codex_telemetry.py' -v
```

The existing Python CI job picks these up automatically. Tests run the real scripts
over the documented JSON hook protocol, without Codex, credentials or network.
They need Python 3.11+, tomlkit, bash and jq. The role installs Arch's
`python-tomlkit`; CI installs `tomlkit>=0.13,<1` for the Python tests.

Shell startup tests use fish and PowerShell when installed (including `pwsh.exe`
under WSL). CI installs fish before running the full Python suite, and runs the
PowerShell case separately on Windows so neither platform's checks depend on
an optional interpreter being present on the other runner.

References: [Codex hooks](https://learn.chatgpt.com/docs/hooks),
[configuration layers](https://learn.chatgpt.com/docs/config-file/config-basic).
