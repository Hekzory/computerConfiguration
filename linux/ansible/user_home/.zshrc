if [[ $LINES -gt 30 ]]; then
    flashfetch
fi

# Enable Powerlevel10k instant prompt. Should stay close to the top of ~/.zshrc.
if [[ -r "${XDG_CACHE_HOME:-$HOME/.cache}/p10k-instant-prompt-${(%):-%n}.zsh" ]]; then
  source "${XDG_CACHE_HOME:-$HOME/.cache}/p10k-instant-prompt-${(%):-%n}.zsh"
fi

HISTFILE=~/.histfile
HISTSIZE=10000
SAVEHIST=10000
setopt autocd extendedglob
unsetopt beep

DISABLE_MAGIC_FUNCTIONS="true"
ENABLE_CORRECTION="true"
COMPLETION_WAITING_DOTS="true"

export HISTCONTROL=ignoreboth
export HISTIGNORE="&:[bf]g:c:clear:history:exit:q:pwd:* --help"

# Use custom `less` colors for `man` pages.
export LESS_TERMCAP_md="$(tput bold 2> /dev/null; tput setaf 2 2> /dev/null)"
export LESS_TERMCAP_me="$(tput sgr0 2> /dev/null)"

# Make new shells get the history lines from all previous
export PROMPT_COMMAND="history -a; $PROMPT_COMMAND"

export FZF_BASE=/usr/share/fzf

# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -

# Set personal aliases, overriding those provided by oh-my-zsh libs,
alias make="make -j`nproc`"
alias ninja="ninja -j`nproc`"

alias mirrorupd="sudo reflector --verbose -l 25  --sort rate --save /etc/pacman.d/mirrorlist"

alias please="sudo"

alias cat='bat --style="auto"'
alias ls='lsd -AhlF --color auto --icon auto'
alias nano='micro'
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
source /usr/share/zsh/plugins/zsh-autosuggestions/zsh-autosuggestions.zsh

# Use history substring search
source /usr/share/zsh/plugins/zsh-history-substring-search/zsh-history-substring-search.zsh

# pkgfile "command not found" handler
# source /usr/share/doc/pkgfile/command-not-found.zsh

# Completions
zstyle ':completion:*' completer _complete _ignored _approximate
zstyle ':completion:*' list-colors "${(s.:.)LS_COLORS}"
zstyle ':completion:*' list-prompt %SAt %p: TAB for more, or the character to insert%s
autoload -Uz compinit
compinit

source /usr/share/zsh/plugins/fast-syntax-highlighting/fast-syntax-highlighting.plugin.zsh

if zmodload zsh/terminfo && (( terminfo[colors] >= 256 )); then
  [[ ! -f ~/.p10k-main.zsh ]] || source ~/.p10k-main.zsh
else
  [[ ! -f ~/.p10k-portable.zsh ]] || source ~/.p10k-portable.zsh
fi
