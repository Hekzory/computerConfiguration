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
| `arch-core.yml` | base packages, pacman/sysctl/makepkg tuning, gitconfig, fish + dotfiles, docker (with NVIDIA detection when present), journald, systemd-resolved, udev rules, kernel module blacklist |
| `arch-desktop.yml` | desktop fonts, kitty, claude-code, chrome, realtime audio group (asserts not WSL) |
| `arch-home.yml` | personal apps (telegram, qbittorrent, vesktop), gaming group |

Run via the wrapper from `linux/ansible/`:

```bash
./run.sh arch-core      # or arch-desktop, or arch-home
```

It validates the playbook name, installs galaxy collections, and runs `ansible-playbook --ask-become-pass`.

### Dotfiles

User-level dotfiles live under `linux/ansible/user_home/` mirroring `$HOME` layout (e.g. `user_home/.config/fish/config.fish` → `~/.config/fish/config.fish`). The "Deploy dotfiles" task in `arch-core.yml` auto-discovers the whole tree (via `community.general.filetree`) and deploys it — adding a dotfile is just dropping the file under `user_home/`, no playbook edit needed.

### Requirements

- Arch Linux or CachyOS
- `ansible` (`pacman -S ansible`)
- User in `wheel` for sudo

## Windows

Declarative configuration via WinGet Configuration at `windows/configuration.winget`, run on DSC v3 (winget installs it from the Store on first use). Apply with `winget configure -f windows/configuration.winget` from any terminal: winget asks for elevation once, for the units marked elevated. `winget configure test -f …` shows what is out of state without changing anything. Less actively maintained than the Linux side.

Windows-side dotfiles (`.wslconfig`, and the oh-my-posh theme shared with Linux) live under `windows/home/` and are deployed from the WSL guest: `./run.sh arch-core` there copies them into the Windows profile.

## CI

GitHub Actions runs `ansible-lint` on every push. See `.github/workflows/ansible-lint.yml`.
