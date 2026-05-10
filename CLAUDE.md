# CLAUDE.md

Repo-level guide for agents working in this configuration repo.

## What this is
Personal infrastructure-as-code for keeping Linux (Arch + CachyOS) and Windows machines consistent. Linux uses Ansible; Windows uses DSC. Single-user, single-machine class — no inventory, no fleet management.

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
Live under `linux/ansible/user_home/` mirroring `$HOME` layout. Deployed by the "Copy config files + themes" task in `arch-core.yml`. When adding a dotfile: drop the file under `user_home/`, then add a line to that task's `loop:`. Desktop-specific dotfiles (kitty, zed, chrome) ship via the matching task in `arch-desktop.yml`.

Currently shipped: fish, fastfetch, btop, nvim, kitty, zed, oh-my-posh theme, xdg-desktop-portal, chrome flags.

### Roles
- `roles/requirements.yml` — galaxy collection deps; expand here when new collections are needed.

The `roles/` directory is otherwise empty — most config still lives inline in playbooks. New cross-cutting concerns are candidates for becoming roles, but don't refactor existing tasks into roles speculatively.

### Handlers (in `arch-core.yml`)
Existing event names: `sysctl_changed`, `networkmanager_changed`, `resolved_changed`, `docker_changed`, `initramfs_changed`, `systemd_reload`. Reuse before inventing new ones.

## Conventions

- **Packages**: official-repo first (`community.general.pacman`), AUR via `kewlfft.aur.aur` with `use: yay`. Group with header comments matching the existing style.
- **WSL gating**: hardware/firmware/kernel tasks use `when: not (is_wsl | bool)`. Honor this on additions.
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
