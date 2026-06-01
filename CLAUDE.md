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
- `arch-desktop.yml` — fonts, kitty, zed, chrome (asserts NOT WSL)
- `arch-home.yml` — personal apps (telegram, qbittorrent, vesktop, gaming group)

Run via `./run.sh <arch-core|arch-desktop|arch-home>` from `linux/ansible/`. The wrapper validates args, installs galaxy reqs, and prompts for sudo. Don't invoke `ansible-playbook` directly.

### Dotfiles
Live under `linux/ansible/user_home/` mirroring `$HOME` layout. The "Deploy dotfiles" task in `arch-core.yml` auto-discovers the whole tree via `community.general.filetree` — to add a dotfile, just drop it under `user_home/`; no playbook edit needed. Desktop-only configs (kitty, zed, chrome flags) ship on every machine this way too; that's harmless since the apps themselves are still desktop-gated.

Currently shipped: fish, fastfetch, btop, nvim, kitty, zed, oh-my-posh theme, xdg-desktop-portal, chrome flags.

### Roles
- `roles/requirements.yml` — galaxy collection deps; expand here when new collections are needed.

The `roles/` directory is otherwise empty — most config still lives inline in playbooks. New cross-cutting concerns are candidates for becoming roles, but don't refactor existing tasks into roles speculatively.

### Handlers (in `arch-core.yml`)
Existing event names: `sysctl_changed`, `networkmanager_changed`, `resolved_changed`, `docker_changed`, `initramfs_changed`, `systemd_reload`. Reuse before inventing new ones.

## Conventions

- **Packages**: official-repo first (`community.general.pacman`), AUR via `kewlfft.aur.aur` with `use: yay`. Group with header comments matching the existing style.
- **WSL gating**: hardware/firmware/kernel tasks use `when: not (is_wsl | bool)`. Honor this on additions.
- **Machine-class gating**: battery-sensitive hardware settings vary on the `is_laptop` fact (auto-detected from `/sys/class/power_supply/BAT*`, overridable with `-e is_laptop=...`). These ship as `templates/*.j2` parameterized on `is_laptop` (iwlwifi, SATA/USB/net udev rules). Settings kept for *stability* rather than performance (NVMe APST `default_ps_max_latency_us=0`, NVMe runtime PM in `60-ioschedulers.rules`) are deliberately NOT class-gated — they apply everywhere.
- **Comment tone in YAML**: match what's already there. No corporate-speak.
- **Aliases vs functions vs abbreviations** in fish (`user_home/.config/fish/config.fish`):
  - Destructive ops (`gfuck`, `gpshf`) → functions, ideally with confirmation
  - Common verbs (`g`, `gd`, `gpsh`) → aliases or abbreviations
  - Tool replacements (`cat→bat`) → conditional aliases gated on `type -q`
- **AI-agent awareness**: fish config strips icons/pagers/interactive prompts when `CLAUDECODE` or `CURSOR_TRACE_ID` is set. Preserve this behavior when editing fish config.

## CI
GitHub Actions runs `ansible-lint` on push. Run it locally before committing playbook changes.

## Don't

- Don't run `ansible-playbook` directly — use `run.sh`
- Don't bypass `ansible-lint`
- Don't add backwards-compat shims for removed config — the playbook is idempotent and reruns on bare installs, not migrated
- Don't speculatively pull in plugin frameworks (fisher, oh-my-fish, etc.). The setup is intentionally low-dep and composable from base packages.
