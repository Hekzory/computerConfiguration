if [[ $LINES -gt 30 ]]; then
    flashfetch
fi
# Enable Powerlevel10k instant prompt. Should stay close to the top of ~/.zshrc.
# Initialization code that may require console input (password prompts, [y/n]
# confirmations, etc.) must go above this block; everything else may go below.
if [[ -r "${XDG_CACHE_HOME:-$HOME/.cache}/p10k-instant-prompt-${(%):-%n}.zsh" ]]; then
  source "${XDG_CACHE_HOME:-$HOME/.cache}/p10k-instant-prompt-${(%):-%n}.zsh"
fi

# Enable Wayland support for different applications
if [ "$XDG_SESSION_TYPE" = "wayland" ]; then
    export WAYLAND=1
#    export QT_QPA_PLATFORM='wayland;xcb'
#    export GDK_BACKEND='wayland,x11'
#    export MOZ_DBUS_REMOTE=1
#    export MOZ_ENABLE_WAYLAND=1
    export _JAVA_AWT_WM_NONREPARENTING=1
#    export BEMENU_BACKEND=wayland
#    export CLUTTER_BACKEND=wayland
#    export ECORE_EVAS_ENGINE=wayland_egl
#    export ELM_ENGINE=wayland_egl
fi


HISTFILE=~/.histfile
HISTSIZE=10000
SAVEHIST=10000
setopt autocd extendedglob
unsetopt beep

# Uncomment the following line if pasting URLs and other text is messed up.
DISABLE_MAGIC_FUNCTIONS="true"

# Uncomment the following line to enable command auto-correction.
ENABLE_CORRECTION="true"

# Uncomment the following line to display red dots whilst waiting for completion.
COMPLETION_WAITING_DOTS="true"

# User configuration

# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -

# Ignore commands that start with spaces and duplicates.

export HISTCONTROL=ignoreboth

# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -

# Don't add certain commands to the history file.

export HISTIGNORE="&:[bf]g:c:clear:history:exit:q:pwd:* --help"

# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -

# Use custom `less` colors for `man` pages.

export LESS_TERMCAP_md="$(tput bold 2> /dev/null; tput setaf 2 2> /dev/null)"
export LESS_TERMCAP_me="$(tput sgr0 2> /dev/null)"

# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -

# Make new shells get the history lines from all previous
# shells instead of the default "last window closed" history.

export PROMPT_COMMAND="history -a; $PROMPT_COMMAND"

# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -

# Set personal aliases, overriding those provided by oh-my-zsh libs,
# plugins, and themes. Aliases can be placed here, though oh-my-zsh
# users are encouraged to define aliases within the ZSH_CUSTOM folder.
#alias open="xdg-open"
alias make="make -j`nproc`"
alias ninja="ninja -j`nproc`"
#alias n="ninja"
#alias c="clear"

alias mirrorupd="sudo reflector --verbose -l 25  --sort rate --save /etc/pacman.d/mirrorlist"

alias please="sudo"

alias cat='bat --style="auto"'
alias ls='lsd -AhlF --color auto --icon auto'
alias nano='nano -c -S -u -l'
alias rm='rm -i'
alias cp='cp -i'
alias mv='mv -i'
alias less='less -r'
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

source /usr/share/zsh-theme-powerlevel10k/powerlevel10k.zsh-theme

# Fish-like syntax highlighting and autosuggestions
source /usr/share/zsh/plugins/zsh-syntax-highlighting/zsh-syntax-highlighting.zsh
source /usr/share/zsh/plugins/zsh-autosuggestions/zsh-autosuggestions.zsh

# Use history substring search
source /usr/share/zsh/plugins/zsh-history-substring-search/zsh-history-substring-search.zsh

# pkgfile "command not found" handler
# source /usr/share/doc/pkgfile/command-not-found.zsh

# Completions
zstyle ':completion:*' completer _complete _ignored _approximate
zstyle ':completion:*' list-colors ''
zstyle ':completion:*' list-prompt %SAt %p: TAB for more, or the character to insert%s
autoload -Uz compinit
compinit

# To customize prompt, run `p10k configure` or edit ~/.p10k.zsh.
#[[ ! -f ~/.p10k.zsh ]] || source ~/.p10k.zsh

if zmodload zsh/terminfo && (( terminfo[colors] >= 256 )); then
  [[ ! -f ~/.p10k-main.zsh ]] || source ~/.p10k-main.zsh
else
  [[ ! -f ~/.p10k-portable.zsh ]] || source ~/.p10k-portable.zsh
fi

export FZF_BASE=/usr/share/fzf
