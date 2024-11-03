# Initializing some environment variables earlier:
set -gx EDITOR nvim
set -gx PAGER less
set -gx MANROFFOPT "-c"
set -gx MANPAGER "sh -c 'col -bx | bat -l man -p'"

function fish_greeting
	if test (tput colors) -ge 256; and test (tput lines) -gt 30
    	flashfetch
	end
end

if test (tput colors) -lt 256
    set -gx LOW_COLOR_SUPPORT 1
end

# Theme handling with error checking
set -g theme_path ~/tokyofine.omp.toml
if not test -f $theme_path
    echo "Downloading missing theme..."
    curl -sL "https://raw.githubusercontent.com/Hekzory/computerConfiguration/master/linux/ansible/user_home/tokyofine.omp.toml" -o $theme_path || echo "Theme download failed!"
end

# Initialize oh-my-posh if available
type -q oh-my-posh && oh-my-posh init fish --config $theme_path | source

# Format man pages


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

# Fish command history
function history
    builtin history --show-time='%F %T '
end

# Set personal aliases, overriding those provided by oh-my-zsh libs,
alias make="make -j"(nproc)""
alias ninja="ninja -j"(nproc)""

alias mrupd="sudo reflector --verbose -l 25  --sort rate --save /etc/pacman.d/mirrorlist"
alias cmrupd="sudo cachyos-rate-mirrors"


alias please="sudo"

alias cat='bat --style=auto'
#alias ls='type -q eza && eza -Ahl --color=auto --icons=auto || ls -lah'
alias ls='eza -Ahl --color=auto --icons=auto'
alias rm='rm -i'
alias cp='cp -i'
alias mv='mv -i'
alias less='less -R'
alias grep='rg -uuu'
alias mkdir="mkdir -pv"
alias pacman="sudo pacman"
alias sctl="sudo systemctl"
alias chown='chown --preserve-root'
alias chmod='chmod --preserve-root'
alias chgrp='chgrp --preserve-root'
alias jerr='journalctl -xb 0 -p 3'
alias jwarn='journalctl -xb 0 -p 4'
alias wget='wget -c'
alias df='duf'
alias top='type -q btop && btop || top'
alias omp='oh-my-posh'

# git part
alias g='git'
alias gundo='git reset --soft HEAD~1'  # Undo last commit, keep changes
alias gfuck='git reset --hard HEAD~1'  # Nuclear option: undo last commit and changes
alias gcar='git commit --amend --reset-author --no-edit' # Update last commit time signature and author
alias gfix='git commit --amend' # smaller amend command
alias gpforce='git push --force' # no comments
alias gpsh='git push' # saving 4 characters, definitely worth it
alias gpll='git pull' # and again
alias gcom='git commit' # and again...


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

# Completion Pager Colors
set -g fish_pager_color_progress $comment
set -g fish_pager_color_prefix $cyan
set -g fish_pager_color_completion $foreground
set -g fish_pager_color_description $comment
set -g fish_pager_color_selected_background --background=$selection


# pnpm
set -gx PNPM_HOME "/home/oleg/.local/share/pnpm"
if not string match -q -- $PNPM_HOME $PATH
  set -gx PATH "$PNPM_HOME" $PATH
end
# pnpm end
