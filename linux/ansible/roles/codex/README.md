# Native Codex configuration

`arch-core` imports this role, including when used by the desktop/home playbooks
or under WSL. Apply from `linux/ansible/` with the usual `./run.sh arch-core`.
This configures Codex; it does not install the CLI or log in for you.

The role deploys root-owned `/etc/codex/config.toml` and two scripts under
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

The role also installs `~/.codex/rules/claude-import.rules`, a selected global
import of Claude command approvals: `nvim --version`, `tree-sitter --version`,
`/bin/ls` and `pnpm build`. Matching commands may run outside the sandbox without
prompting in any project for this user.
Rules match argument prefixes, so extra arguments are permitted too. Inline
`match` and `not_match` examples are checked by Codex when the file loads.
The `pnpm build` approval permits package-defined build scripts in any repository.
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
So do `~/.codex/config.toml`, auth files, user/project hooks, MCP servers and
`requirements.toml`. The system config is a defaults layer, not a replacement for
user settings: a higher-precedence footer choice still wins, and explicitly
turning off `features.hooks` at a higher layer disables hooks. System hooks are
managed/trusted by Codex; no hook-trust bypass is used.

A pre-existing `/etc/codex/config.toml` without this role's ownership marker (or a
symlink) stops deployment before writing anything. Review existing system settings
before adopting the role; it will not silently overwrite an employer's config.
Later runs update the managed files idempotently. Hook scripts are installed
before the configuration, whose TOML is validated before replacement.

Start a new Codex session after deployment and inspect `/hooks` for both handlers.
Use a recent CLI with `PreToolUse` support. A hook error/timeout is not a guaranteed
denial, so these checks must not be mistaken for a sandbox.

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
```

The existing Python CI job picks these up automatically. Tests run the real scripts
over the documented JSON hook protocol, without Codex, credentials or network.
They need Python 3.11+, bash and jq (already shipped by arch-core).

Shell startup tests use fish and PowerShell when installed (including `pwsh.exe`
under WSL). CI installs fish before running the full Python suite, and runs the
PowerShell case separately on Windows so neither platform's checks depend on
an optional interpreter being present on the other runner.

References: [Codex hooks](https://learn.chatgpt.com/docs/hooks),
[configuration layers](https://learn.chatgpt.com/docs/config-file/config-basic).
