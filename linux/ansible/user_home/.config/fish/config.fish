# Early environment variables
set -gx EDITOR nvim
set -gx PAGER "less -R"
set -gx MANROFFOPT "-c"
set -gx MANPAGER "sh -c 'col -bx | bat -l man -p'"

# I use kitty, but can't guarantee that its' terminfo will be present on remote host, so need to be safe
if test "$TERM" = "xterm-kitty"
    set -gx TERM xterm-256color
end

# tput fails (empty stdout, non-zero exit) when $TERM is unset — happens on some
# non-interactive SSH/agent invocations. Treat "unknown" as low-color.
set -l _colors (tput colors 2>/dev/null)
if test -z "$_colors"; or test "$_colors" -lt 256
    set -gx LOW_COLOR_SUPPORT 1
end

if status is-interactive
    function fish_greeting
        # Skip greeting in editor terminals, AI agent shells, nested shells, and dumb terminals.
        # AI agents parse the banner as wasted tokens; nested shells (nvim :term, `fish` in fish) don't need it.
        test "$TERM_PROGRAM" = vscode; and return
        test "$TERMINAL_EMULATOR" = JetBrains-JediTerm; and return
        set -q CLAUDECODE; and return
        set -q CURSOR_TRACE_ID; and return
        test -z "$TERM"; and return
        test "$TERM" = dumb; and return
        test "$SHLVL" -gt 1; and return

        if type -q fastfetch; and test (tput colors) -ge 256; and test (tput lines) -gt 25
            fastfetch
        end
    end

    # Theme handling with error checking
    set -g theme_path ~/tokyofine.omp.toml
    if not test -f $theme_path
        echo "🔄 Downloading missing theme..."
        curl -sL "https://raw.githubusercontent.com/Hekzory/computerConfiguration/master/linux/ansible/user_home/tokyofine.omp.toml" -o $theme_path || echo "❌ Theme download failed!"
    end

    # Initialize oh-my-posh if available
    if type -q oh-my-posh
        oh-my-posh init fish --config $theme_path | source
    end

    # zoxide: smart cd — `z <substr>` jumps to most-used matching dir, `zi` = interactive fzf pick
    if type -q zoxide
        zoxide init fish | source
    end

end

## Enable Wayland support for different applications
if [ "$XDG_SESSION_TYPE" = "wayland" ]
    set -gx WAYLAND 1
    set -gx QT_QPA_PLATFORM 'wayland;xcb'
    set -gx GDK_BACKEND 'wayland,x11'
    set -gx MOZ_DBUS_REMOTE 1
    set -gx MOZ_ENABLE_WAYLAND 1
    set -gx _JAVA_AWT_WM_NONREPARENTING 1
    set -gx BEMENU_BACKEND wayland
    set -gx CLUTTER_BACKEND wayland
    set -gx ECORE_EVAS_ENGINE wayland_egl
    set -gx ELM_ENGINE wayland_egl
end

# Fish command history — preserve $argv so `history search`, `history delete`, etc. still work
function history --wraps history --description "history with timestamps"
    builtin history --show-time='%F %T ' $argv
end

# Set personal aliases
function make
    command make -j(nproc) $argv
end

function ninja
    command ninja -j(nproc) $argv
end

alias mrupd="sudo reflector --verbose -l 25  --sort rate --save /etc/pacman.d/mirrorlist"
alias cmrupd="sudo cachyos-rate-mirrors"

if type -q bat
    alias cat='bat --style=auto --paging=never'
end
if type -q eza
    alias ls='eza -Ahl --color=auto --icons=auto'
end
alias rm='rm -i'
alias cp='cp -i'
alias mv='mv -i'
alias less='less -R'
alias mkdir="mkdir -pv"
alias pacman="sudo pacman"
alias sctl="sudo systemctl"
alias chown='chown --preserve-root'
alias chmod='chmod --preserve-root'
alias chgrp='chgrp --preserve-root'
alias jerr='journalctl -xb 0 -p 3'
alias jwarn='journalctl -xb 0 -p 4'
alias wget='wget -c'
if type -q duf
    alias df='duf'
end
if type -q btop
    alias top='btop'
end
alias omp='oh-my-posh'

if type -q wl-copy  # Wayland
    alias yank='wl-copy'
end

# grep intentionally left alone — `rg` has different regex/output semantics

# Under an AI agent: drop aliases that stall (interactive -i prompts, sudo prompts,
# full-screen TUIs) or waste tokens (icons, ANSI, box-drawing). Where the modern
# tool can be tuned to still beat the classic, keep it; otherwise fall through.
if set -q CLAUDECODE; or set -q CURSOR_TRACE_ID
    # Bare commands are leanest — no usable tuned variant exists for these
    functions --erase rm cp mv cat df top pacman sctl
    # Destructive git wrappers prompt interactively; would deadlock under agents
    functions --erase gfuck gpshf

    # eza tuned: ISO dates, no icons/ANSI, `-` for dir sizes — more compact than `ls -Ahl`
    if type -q eza
        alias ls='eza -Ahl --color=never --icons=never --time-style=long-iso'
    end

    # Keep -p (prevents retry on missing parent), drop -v (per-dir spam)
    alias mkdir='mkdir -p'

    # Pagers auto-invoke on PTY even in agent sessions — force non-paging output
    set -gx PAGER cat
    set -gx SYSTEMD_PAGER cat
    set -gx MANPAGER 'col -bx'
end

# Git aliases + functions live in conf.d/git-helpers.fish

# TokyoNight Color Palette
set -l foreground c8d3f5
set -l selection 2d3f76
set -l comment 636da6
set -l red ff757f
set -l orange ff966c
set -l yellow ffc777
set -l green c3e88d
set -l purple fca7ea
set -l cyan 86e1fc
set -l pink c099ff

# Syntax Highlighting Colors
set -g fish_color_normal $foreground
set -g fish_color_command $cyan
set -g fish_color_keyword $pink
set -g fish_color_quote $yellow
set -g fish_color_redirection $foreground
set -g fish_color_end $orange
set -g fish_color_error $red
set -g fish_color_param $purple
set -g fish_color_comment $comment
set -g fish_color_selection --background=$selection
set -g fish_color_search_match --background=$selection
set -g fish_color_operator $green
set -g fish_color_escape $pink
set -g fish_color_autosuggestion $comment
set -g fish_color_separator --dimmed

# Completion Pager Colors
set -g fish_pager_color_progress $comment
set -g fish_pager_color_prefix $cyan
set -g fish_pager_color_completion $foreground
set -g fish_pager_color_description $comment
set -g fish_pager_color_selected_background --background=$selection


fish_add_path -g $HOME/.local/bin

# pnpm
set -gx PNPM_HOME "$HOME/.local/share/pnpm"
fish_add_path -g $PNPM_HOME
# pnpm end

# Load custom.fish config if it exists
if test -f ~/.config/fish/custom.fish
    source ~/.config/fish/custom.fish
end

bind \cf 'fzf | read -l result; and commandline -i $result'  # Ctrl+F for fuzzy file search
