# CLAUDE.md

Repo-level guide for agents working in this configuration repo.

## What this is
Personal infrastructure-as-code for keeping Linux (Arch + CachyOS) and Windows machines consistent. Linux uses Ansible; Windows uses WinGet Configuration on DSC v3. Single user, runs locally on each machine — no inventory, no fleet management. Two hardware profiles, `laptop` (battery-aware) vs not (performance-first), selected automatically via the `is_laptop` fact.

## Layout
- `linux/ansible/` — primary working area: playbooks, roles, dotfiles
- `windows/configuration.winget` — WinGet Configuration, schema 0.3 on the `dscv3` processor (rarely touched). It mirrors what the Windows box actually has: a package that isn't installed there comes out of the file rather than staying for a fresh install, and settings carry the machine's live values. `winget configure validate`/`test` are read-only; `winget configure export` is not (it installs DSC and PowerShell modules it needs)
- `windows/home/` — Windows-side dotfiles, deployed from WSL by arch-core (see WSL below)
- `vpn-serv/` — separate VPN server configs

## Linux / Ansible
Three layered playbooks, each importing the previous:

- `arch-core.yml` — base system: pacman config, packages, sysctl, gitconfig, fish + dotfiles, native Codex, optional Claude, docker, NVIDIA detect, journald, systemd-resolved
- `arch-desktop.yml` — fonts, kitty, mpv, chrome (asserts NOT WSL)
- `arch-home.yml` — personal apps (telegram, qbittorrent, vesktop, gaming group)

Run via `./run.sh <arch-core|arch-desktop|arch-home>` from `linux/ansible/`. The wrapper validates args, installs galaxy reqs (going on with the installed ones when Galaxy is unreachable), and authenticates sudo once up front (`sudo -v`, kept alive in the background) — ansible itself runs `sudo -n`, so PAM (and pam_fprintd on laptops) is hit once per run, not once per task. That only works with the user-wide sudo ticket from `etc/sudoers.d/10-timestamp-global` (ansible workers `setsid()` away from the terminal), which run.sh bootstraps and the playbook manages. Don't invoke `ansible-playbook` directly and don't bring back `--ask-become-pass`.

### Dotfiles
Live under `linux/ansible/user_home/` mirroring `$HOME` layout. The "Deploy dotfiles" task in `arch-core.yml` auto-discovers the whole tree via `community.general.filetree` — to add a dotfile, just drop it under `user_home/`; no playbook edit needed. Desktop-only configs (kitty, chrome flags) ship on every machine this way too; that's harmless since the apps themselves are still desktop-gated.

Currently shipped: fish, fastfetch, btop, nvim, kitty, mpv (uosc UI), zed, oh-my-posh theme, xdg-desktop-portal, chrome flags. Claude helpers and completions live under `roles/claude/files/user_home/` and ship only with `--claude`.

The mpv config in the repo is only what suits every machine. Anything tuned to one box (scalers and shaders for a weak iGPU, panel bit depth, stream height cap, hwdec order for a specific driver) goes into `~/.config/mpv/local.conf` on that machine, outside the repo: `mpv.conf` includes it at the end of its top-level section, and `arch-desktop.yml` seeds an empty one.

The zed config is deliberately orphaned — the editor was dropped from `arch-desktop.yml` (and is uninstalled by its cleanup task), but the config stays deployed in case it comes back. Don't "fix" the mismatch by deleting one or restoring the other.

Files ending in `.sh` land as `0750` instead of the usual read-only mode — helper scripts other tools shell out to are useless without `+x`.

### Claude Code (opt-in)
`roles/claude` owns Claude Code, ccodex, user helpers/completions, managed policy,
telemetry and mods. It runs only with `./run.sh <playbook> --claude`, independently
of `--corporate`; both flags can be combined in either order. Ordinary runs do
not install, update, or remove an existing Claude setup. See
[`roles/claude/README.md`](linux/ansible/roles/claude/README.md) for details.

The SSH-to-fish guard is shared in `files/ssh-fish-guard.py`; native Codex still
installs its own copy without enabling Claude. Shared writing preferences for
Codex remain unconditional; Claude's copy belongs to the opt-in role.

### WSL
`roles/wsl`, included from arch-core when `is_wsl`, owns what exists only because this is WSL: the distro's `/etc/wsl.conf` and, through interop, the Windows host's dotfiles. `windows/home/` mirrors the Windows profile with the known folder as the first path segment (`USERPROFILE/.wslconfig`; `Documents`, `APPDATA` and `LOCALAPPDATA` work the same way). One `powershell.exe` call resolves the folders (Documents is redirected to `D:` on this box) and `wslpath` maps them. As with `user_home/`, dropping a file in ships it. Shipped so far: `.wslconfig`, the PowerShell 7 profile, Windows Terminal Preview's `settings.json` and fastfetch's config (its own module list, not the Linux one). A file Windows shares with Linux, like the oh-my-posh theme, is listed in `wsl_windows_shared` and goes out from `user_home/` instead of a second copy; its folder has to exist already. Terminal's settings UI saves into the shipped file, so the next run undoes a change made there: make it in the repo. The `0755`/`0644` modes the role sets only land in WSL's metadata and leave the NTFS ACLs alone, packaged apps' folders under `LOCALAPPDATA/Packages` included. Everything is copied, never linked: a link from Windows into the distro is a reparse point Windows can't read. `wsl.conf` and `.wslconfig` are read only when WSL starts and the play runs inside it, so a change to either prints a reminder to run `wsl --shutdown` from Windows. `/etc/resolv.conf` is written by hand (home DNS first), which is why `wsl.conf` keeps `generateResolvConf = false`.

The WSL role also installs `tcodex`, which runs the installed `codex` with the same
arguments and inherited fish completions. It queries terminal cell pixels and
maintains a PTY with real pixel dimensions, enabling Codex's Sixel previews in
Windows Terminal. Window resizes requery the terminal, including font changes
when they cause a resize. Pipelines and redirected streams run Codex directly.
Only Python's standard library is needed; ordinary `codex` remains available.

For the verified Arch Codex 0.169.0 build, `tcodex` also caches a binary copy with
12×6-cell draft thumbnails (twice the original width and height). The patch checks
the complete original/result SHA-256 hashes and all 22 instruction sites; unknown
builds run unmodified with a notice. The package's binary and resources stay in
place. The roughly 301 MiB copy persists under `$XDG_CACHE_HOME/tcodex` (normally
`~/.cache/tcodex`); concurrent launches share it. `TCODEX_PREVIEW_PATCH=0 tcodex`
disables the binary patch. Maintenance commands such as `tcodex update` use the
installed executable.

### Terminal colors
Programs decide on 24-bit color from `COLORTERM=truecolor`, and Windows Terminal doesn't set it by itself, so without help everything under WT (Claude Code included) rounds to 256 colors. WT's shipped settings set it in `profiles.defaults.environment`, which covers native Windows programs. That doesn't reach WSL, where `WSLENV` forwards only `WT_SESSION`, so `config.fish` sets it when `WT_SESSION` is present; kitty sets it itself. ssh carries `TERM` but not `COLORTERM`, so `etc/ssh/ssh_config.d/30-colorterm.conf` sends it and `etc/ssh/sshd_config.d/30-colorterm.conf` accepts it. Both halves ship everywhere, and the sshd reload only happens where sshd is running. Remote sessions get 24-bit color only once both ends have run the playbook.

### Ananicy
`cachyos-ananicy-rules` is the upstream set; personal overrides live in `etc/ananicy.d/zz-personal.rules` (same rule names, different values). ananicy-cpp loads files in readdir order and the last definition wins, so `usr/local/bin/ananicy-mask-upstream` comments the upstream twins out; the playbook runs it and a pacman hook reruns it after every rules upgrade. To change an override, edit the rules file and rerun the playbook — never edit files under `00-default/` by hand and never pin them with `NoUpgrade` (the hook would have nothing to re-mask). The upstream `Games/` ruleset is dropped everywhere (`NoExtract` in pacman.conf plus removal of the already-extracted dir). Machine-local extras go in another top-level `/etc/ananicy.d/*.rules` with non-overlapping names, outside the repo.

### Output
`run.sh` runs with `-v`; the stdout callback is the repo's `callback_plugins/quiet_ok.py` (ansible.posix `debug` with the result dump muted for unchanged tasks, wired in `ansible.cfg`). Changed/failed/unreachable still print their details (with oversized fields trimmed below `-vvv`), while ok/skipped results stay on one line. Command stdout and diffs remain visible for changed tasks. Don't add `no_log` just to quiet a noisy task.

### Roles
- `roles/requirements.yml` — galaxy collection deps; expand here when new collections are needed.

Apart from `roles/wsl` (see WSL above), most config still lives inline in playbooks. New cross-cutting concerns are candidates for becoming roles, but don't refactor existing tasks into roles speculatively.

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
- **AI-agent awareness**: fish and PowerShell recognize `CLAUDECODE`, `CURSOR_TRACE_ID`, `CODEX_THREAD_ID` and `CODEX_CI`. Agent shells skip banners and prompt themes and disable pagers and Git credential prompts; fish also strips interactive wrappers and icons. Preserve this behavior when editing either shell. The PowerShell profile in `windows/home` also skips the banner and theme for a `-Command`/`-File` run or redirected output. Native Codex defaults are documented in `linux/ansible/roles/codex/README.md`.

## CI
GitHub Actions runs `ansible-lint` and the main shell/Fish/Python checks on PRs.
Run `ansible-lint` locally before committing playbook changes when Linux tooling
is available; always keep the CI gate enabled. `claude-mods.yml` is path-filtered
to the optional role and shared SSH guard: shell/JS/Python/JSON checks and offline
ccodex tests only. No latest-version matrix, Claude download, or weekly schedule.

## Don't

- Don't run `ansible-playbook` directly — use `run.sh`
- Don't bypass `ansible-lint`
- Don't add backwards-compat shims for removed config — the playbook is idempotent and reruns on bare installs, not migrated
- Don't speculatively pull in plugin frameworks (fisher, oh-my-fish, etc.). The setup is intentionally low-dep and composable from base packages.
