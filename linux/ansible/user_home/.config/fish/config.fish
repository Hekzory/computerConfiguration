function fish_greeting
	flashfetch
end

oh-my-posh init fish | source

#if status is-interactive
    # Commands to run in interactive sessions can go here
#end

# Format man pages
set -x MANROFFOPT "-c"
set -x MANPAGER "sh -c 'col -bx | bat -l man -p'"

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
alias make="make -j`nproc`"
alias ninja="ninja -j`nproc`"

alias mrupd="sudo reflector --verbose -l 25  --sort rate --save /etc/pacman.d/mirrorlist"
alias cmrupd="sudo cachyos-rate-mirrors"


alias please="sudo"

alias cat='bat --style="auto"'
alias ls='eza -Ahl --color auto --icons auto'
alias rm='rm -i'
alias cp='cp -i'
alias mv='mv -i'
alias less='less -R'
alias grep="grep -n --color"
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
alias htop='btop'
alias top='btop'
alias grep='rg -uuu'
alias omp='oh-my-posh'


