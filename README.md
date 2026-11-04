# computerConfiguration

[![ansible-lint](https://github.com/Hekzory/computerConfiguration/actions/workflows/ansible-lint.yml/badge.svg?event=push)](https://github.com/Hekzory/computerConfiguration/actions/workflows/ansible-lint.yml)

Personal infrastructure-as-code for keeping my Linux and Windows machines consistent. Single user, run locally on each machine — no inventory, no fleet management. Two hardware profiles, laptop (battery-aware) vs not (performance-first), are selected automatically: a laptop is detected from battery presence (`is_laptop`), and the battery-hostile-for-no-reason tweaks (WiFi power saving, SATA/USB/ethernet link power) relax accordingly.

## Layout

- `linux/ansible/` — Ansible playbooks and dotfiles for Arch Linux (with CachyOS extras)
- `windows/configuration.winget` — Windows configuration (WinGet Configuration on DSC v3)
- `vpn-serv/` — VPN server config

## Linux (Arch / CachyOS)

Three layered playbooks under `linux/ansible/`, each importing the previous:

| Playbook | What it covers |
|----------|----------------|
| `arch-core.yml` | base packages, pacman/sysctl/makepkg tuning, gitconfig, fish + dotfiles, native Codex, docker (with NVIDIA detection when present), journald, systemd-resolved, udev rules, kernel module blacklist |
| `arch-desktop.yml` | desktop fonts, kitty, chrome, realtime audio group (asserts not WSL) |
| `arch-home.yml` | personal apps (telegram, qbittorrent, vesktop), gaming group |

Run via the wrapper from `linux/ansible/`:

```bash
./run.sh arch-core      # or arch-desktop, or arch-home
./run.sh arch-core --corporate  # opt in to corporate Codex setup; works with all three
./run.sh arch-desktop --claude  # opt in to Claude Code and ccodex
./run.sh arch-home --corporate --claude  # optional roles can be combined
```

It validates the playbook name, installs galaxy collections, and asks for the sudo password once up front, so the run prompts only once (and a fingerprint reader is touched once, not per task).

`--corporate` enables the separate corporate Codex role inside the selected
playbook's `arch-core` setup. It requires the private inputs described in
[`roles/codex_corporate`](linux/ansible/roles/codex_corporate/README.md).
Without the flag, corporate provisioning is skipped; existing integrations are
preserved.

### Optional Claude Code

`./run.sh arch-core --claude` installs and configures Claude Code, ccodex,
helpers, managed policy, telemetry and mods through the separate
[`claude` role](linux/ansible/roles/claude/README.md). The flag works with all
three playbooks and combines with `--corporate` in either order. Without it,
Claude provisioning is skipped and existing installations and credentials stay
as they are. Native Codex remains part of the default setup.

### Dotfiles

User-level dotfiles live under `linux/ansible/user_home/` mirroring `$HOME` layout (e.g. `user_home/.config/fish/config.fish` → `~/.config/fish/config.fish`). The "Deploy dotfiles" task in `arch-core.yml` auto-discovers the whole tree (via `community.general.filetree`) and deploys it — adding a dotfile is just dropping the file under `user_home/`, no playbook edit needed.

### Requirements

- Arch Linux or CachyOS
- `ansible` (`pacman -S ansible`)
- User in `wheel` for sudo

## Windows

Declarative configuration via WinGet Configuration at `windows/configuration.winget`, run on DSC v3 (winget installs it from the Store on first use). Apply with `winget configure -f windows/configuration.winget` from any terminal: winget asks for elevation once, for the units marked elevated. `winget configure test -f …` shows what is out of state without changing anything. Less actively maintained than the Linux side.

Windows-side dotfiles (`.wslconfig`, the PowerShell 7 profile, Windows Terminal's settings, fastfetch's config) live under `windows/home/` and are deployed from the WSL guest: `./run.sh arch-core` there copies them into the Windows profile, together with the oh-my-posh theme it shares with Linux. Terminal's settings UI writes to the same file, so a change made there lasts until the next run; make it in the repo instead.

## CI

GitHub Actions keeps the main Ansible and shell/Fish/Python checks. The optional Claude role has a separate path-filtered workflow with static checks and offline ccodex tests; no Claude installation, latest-version matrix, or weekly runs.
