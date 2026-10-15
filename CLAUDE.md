# CLAUDE.md

Repo-level guide for agents working in this configuration repo.

## What this is
Personal infrastructure-as-code for keeping Linux (Arch + CachyOS) and Windows machines consistent. Linux uses Ansible; Windows uses DSC. Single user, runs locally on each machine — no inventory, no fleet management. Two hardware profiles, `laptop` (battery-aware) vs not (performance-first), selected automatically via the `is_laptop` fact.

## Layout
- `linux/ansible/` — primary working area: playbooks, roles, dotfiles
- `windows/configuration.dsc.yaml` — Windows DSC (rarely touched)
- `vpn-serv/` — separate VPN server configs

## Linux / Ansible
Three layered playbooks, each importing the previous:

- `arch-core.yml` — base system: pacman config, packages, sysctl, gitconfig, fish + dotfiles, docker, NVIDIA detect, journald, systemd-resolved
- `arch-desktop.yml` — fonts, kitty, mpv, claude-code, chrome (asserts NOT WSL)
- `arch-home.yml` — personal apps (telegram, qbittorrent, vesktop, gaming group)

Run via `./run.sh <arch-core|arch-desktop|arch-home>` from `linux/ansible/`. The wrapper validates args, installs galaxy reqs, and authenticates sudo once up front (`sudo -v`, kept alive in the background) — ansible itself runs `sudo -n`, so PAM (and pam_fprintd on laptops) is hit once per run, not once per task. That only works with the user-wide sudo ticket from `etc/sudoers.d/10-timestamp-global` (ansible workers `setsid()` away from the terminal), which run.sh bootstraps and the playbook manages. Don't invoke `ansible-playbook` directly and don't bring back `--ask-become-pass`.

### Dotfiles
Live under `linux/ansible/user_home/` mirroring `$HOME` layout. The "Deploy dotfiles" task in `arch-core.yml` auto-discovers the whole tree via `community.general.filetree` — to add a dotfile, just drop it under `user_home/`; no playbook edit needed. Desktop-only configs (kitty, chrome flags) ship on every machine this way too; that's harmless since the apps themselves are still desktop-gated.

Currently shipped: fish, fastfetch, btop, nvim, kitty, mpv (uosc UI), zed, oh-my-posh theme, xdg-desktop-portal, chrome flags, claude (statusline, commit-attribution guard, metrics header helper). The Claude Code mods are not dotfiles: they go to `/etc`, see Claude Code below.

The mpv config in the repo is only what suits every machine. Anything tuned to one box (scalers and shaders for a weak iGPU, panel bit depth, stream height cap, hwdec order for a specific driver) goes into `~/.config/mpv/local.conf` on that machine, outside the repo: `mpv.conf` includes it at the end of its top-level section, and `arch-desktop.yml` seeds an empty one.

The zed config is deliberately orphaned — the editor was dropped from `arch-desktop.yml` (and is uninstalled by its cleanup task), but the config stays deployed in case it comes back. Don't "fix" the mismatch by deleting one or restoring the other.

Files ending in `.sh` land as `0750` instead of the usual read-only mode — helper scripts other tools shell out to are useless without `+x`.

### Claude Code
Split in two on purpose: the helper scripts are dotfiles under `user_home/.claude/`, the settings that point at them are a *policy* drop-in at `/etc/claude-code/managed-settings.d/10-claude-personal.json` (rendered from `templates/`).

`~/.claude/settings.json` is never touched — it holds API tokens and proxy env on work machines and must stay out of git. Policy settings outrank user and project ones, so `attribution` (empty = no Co-Authored-By, no PR trailer, no session link) can't be flipped by a per-repo settings file. Same for `promptSuggestionEnabled` and `awaySummaryEnabled` (both `false`): every suggestion and recap is a hidden main-model request over the whole context. Model and effort deliberately stay out of the policy file so `/model` and `/effort` keep working.

Usage metrics are a second drop-in, `20-claude-telemetry.json`: OTLP metrics (no logs, no traces) to `https://otel.tsv.one/v1/metrics`, which lands in VictoriaMetrics on o-srv and the "Claude Code" dashboard on grafana.tsv.one, one instance per `host.name` (`claude_otel_host`: the hostname, `-wsl` appended under WSL). It is opt-in per machine: the drop-in ships only where `~/.claude/otel-token` exists, and is removed everywhere else. The token never enters git or `/etc` — `otel-headers.sh` (the `otelHeadersHelper`) reads it at runtime, so it also stays out of the env every Claude command inherits. The playbook also leaves telemetry off when any managed or user settings file already mentions `OTEL_`/telemetry: a later drop-in overrides an employer policy key by key and would silently steal the employer's telemetry. Server side (token check, the store, the dashboard) lives in the private nginx-gateway and monitoring repos.

To turn metrics on for a machine (`<o-srv>` = the home server, kept out of this public repo):
```fish
ssh <o-srv> make -sC nginx-gateway otel-token | install -m600 /dev/stdin ~/.claude/otel-token
./run.sh arch-core
```
Running sessions keep their old settings; new ones export. Delete the token file and rerun to turn it off.

The spend meter (github.com/Hekzory/spend-meter, a pane with the session's cost) is a third drop-in, `30-claude-spend-meter.json`: it declares the plugin's GitHub marketplace with `autoUpdate: true` and enables the plugin, so every machine installs it and picks up each release on startup (Claude Code auto-updates only Anthropic's own marketplaces by default). It is left out, and removed, on a machine that runs the mod from a working copy (a folder marketplace named `spend-meter` in `~/.claude/settings.json`), which policy would otherwise switch to GitHub, and on one whose policy sets `strictKnownMarketplaces`. Drop-ins deep-merge, so its `extraKnownMarketplaces` entry adds to an employer's rather than replacing them.

lean-harness (`etc/claude-code/mods/plugins/lean-harness`) trims what every request re-reads; together with the skill overrides and the Docs deny below that is about 9.6k tokens of a 44k prefix. It moves three rarely used tools behind ToolSearch (ScheduleWakeup, SendFeedback, ReportFindings) and names them in one prompt line. It drops product blurbs, the idle `<total_tokens>` line and its per-request reminder, and Fable's identity blurb. It hides the `statusline-setup` agent, since policy owns the status line. It only touches what ships with Claude Code: an agent, MCP server or plugin added on the machine passes through untouched, even under a trimmed name. The skill listing is trimmed by policy, not by the mod: `skillOverrides` in `10-claude-personal.json` keeps built-ins you start yourself out of the model's view (they still run as `/name`), lists claude.ai's file-format and research skills by name only and turns off the ones these machines can't use. It is keyed by bare name, so a personal or project skill must not reuse one of those names (plugin skills are namespaced and unaffected), and `/skills` shows them as set by policy. Only a plugin policy seats may rewrite the prompt (on a machine with managed settings the built-in sec-default skips the prompt hooks of anything a user installs), so the playbook copies the mod to `/etc/claude-code/mods` (a folder marketplace, root-owned) and a fourth drop-in, `40-claude-lean-harness.json`, seats it with `prependPlugins`. That list replaces Claude Code's default, so it names `sec-default@builtin` again, and the drop-in is left out where another policy sets the tier lists or allowlists marketplaces. The Claude Docs connector is denied by name in `10-claude-personal.json`; Claude Code joins `deniedMcpServers` from every policy source, and a connector added on claude.ai later still loads.

Its tests run in CI (`.github/workflows/claude-mods.yml`) on two versions: the newest one the fixtures hold a capture of, and npm's `latest`, weekly too. `claude plugin test plugins/lean-harness` checks the rules against captured fixtures, one per Claude Code version, and fails when a rule's target is gone from the newest one. `tests/live/check.mjs` runs the real Claude Code against a stand-in Messages API, once as shipped and once with the mod seated, for every model. It fails unless the two requests differ by exactly the rules and the skill overrides, with a planted skill, an agent, a plugin and an MCP server coming through unchanged, and unless every override still names a skill the newest fixture lists. It needs no account, and it gets its own `/etc/claude-code` from a user namespace, or from sudo under CI. When Claude Code updates on the machines, run `python3 tests/live/capture.py` on a logged-in machine: one Haiku request writes `tests/fixtures/v<version>.ts` as shipped (the mod, the overrides and the Docs deny left out; home folder, user name and e-mail scrubbed); review the diff and commit it. A red `latest` leg means a rule needs updating in `hooks/register.js` or the template before the machines get that version.

Skills and MCP config are not shipped: the ones on the work laptop are all corporate. This repo is public — keep it that way.

### Terminal colors
Programs decide on 24-bit color from `COLORTERM=truecolor`, and Windows Terminal never sets it, so under WT everything (Claude Code included) rounds to 256 colors. `config.fish` sets it when `WT_SESSION` is present (WT forwards that into WSL through `WSLENV`); kitty sets it itself. ssh carries `TERM` but not `COLORTERM`, so `etc/ssh/ssh_config.d/30-colorterm.conf` sends it and `etc/ssh/sshd_config.d/30-colorterm.conf` accepts it. Both halves ship everywhere, and the sshd reload only happens where sshd is running. Remote sessions get 24-bit color only once both ends have run the playbook.

### Ananicy
`cachyos-ananicy-rules` is the upstream set; personal overrides live in `etc/ananicy.d/zz-personal.rules` (same rule names, different values). ananicy-cpp loads files in readdir order and the last definition wins, so `usr/local/bin/ananicy-mask-upstream` comments the upstream twins out; the playbook runs it and a pacman hook reruns it after every rules upgrade. To change an override, edit the rules file and rerun the playbook — never edit files under `00-default/` by hand and never pin them with `NoUpgrade` (the hook would have nothing to re-mask). The upstream `Games/` ruleset is dropped everywhere (`NoExtract` in pacman.conf plus removal of the already-extracted dir). Machine-local extras go in another top-level `/etc/ananicy.d/*.rules` with non-overlapping names, outside the repo.

### Output
`run.sh` runs with `-v`; the stdout callback is the repo's `callback_plugins/quiet_ok.py` (ansible.posix `debug` with the result dump muted for unchanged tasks, wired in `ansible.cfg`). Changed/failed/skipped still print in full, so command stdout and diffs stay visible where they matter. Don't add `no_log` just to quiet a noisy task.

### Roles
- `roles/requirements.yml` — galaxy collection deps; expand here when new collections are needed.

The `roles/` directory is otherwise empty — most config still lives inline in playbooks. New cross-cutting concerns are candidates for becoming roles, but don't refactor existing tasks into roles speculatively.

### Handlers (in `arch-core.yml`)
Existing event names: `sysctl_changed`, `networkmanager_changed`, `resolved_changed`, `docker_changed`, `initramfs_changed`, `systemd_reload`, `ananicy_changed`, `journald_changed`, `watchdog_changed`, `sshd_changed`. Reuse before inventing new ones.

## Conventions

- **Packages**: official-repo first (`community.general.pacman`), AUR via `kewlfft.aur.aur` with `use: yay`. Group with header comments matching the existing style.
- **WSL gating**: hardware/firmware/kernel tasks use `when: not (is_wsl | bool)`. Honor this on additions. `60-ioschedulers.rules` is the deliberate exception — it ships everywhere, since its NVMe rules are inert without NVMe and it carries the scheduler fix for Hyper-V virtual disks that WSL needs.
- **Machine-class gating**: battery-sensitive hardware settings vary on the `is_laptop` fact (auto-detected from `/sys/class/power_supply/BAT*`, overridable with `-e is_laptop=...`). These ship as `templates/*.j2` parameterized on `is_laptop` (iwlwifi, SATA/USB/net udev rules). Settings kept for *stability* rather than performance (NVMe APST `default_ps_max_latency_us=0`, NVMe runtime PM in `60-ioschedulers.rules`) are deliberately NOT class-gated — they apply everywhere.
- **Comment tone in YAML**: match what's already there. No corporate-speak.
- **Aliases vs functions vs abbreviations** in fish (`user_home/.config/fish/config.fish`):
  - Destructive ops (`gfuck`, `gpshf`) → functions, ideally with confirmation
  - Common verbs (`g`, `gd`, `gpsh`) → aliases or abbreviations
  - Tool replacements (`cat→bat`) → conditional aliases gated on `type -q`
- **AI-agent awareness**: fish config strips icons/pagers/interactive prompts when `CLAUDECODE` or `CURSOR_TRACE_ID` is set. Preserve this behavior when editing fish config.

## CI
GitHub Actions runs `ansible-lint` on push. Run it locally before committing playbook changes. `claude-mods.yml` tests the Claude Code mods under `linux/ansible/etc/claude-code/mods` (see Claude Code above); run `claude plugin test` and `node tests/live/check.mjs` in the plugin folder before committing changes to them.

## Don't

- Don't run `ansible-playbook` directly — use `run.sh`
- Don't bypass `ansible-lint`
- Don't add backwards-compat shims for removed config — the playbook is idempotent and reruns on bare installs, not migrated
- Don't speculatively pull in plugin frameworks (fisher, oh-my-fish, etc.). The setup is intentionally low-dep and composable from base packages.
