if [[ $LINES -gt 30 ]] && zmodload zsh/terminfo && (( terminfo[colors] >= 256 )); then
    flashfetch
fi

if zmodload zsh/terminfo && (( terminfo[colors] < 256 )); then
	export LOW_COLOR_SUPPORT=1
fi

# Check if the theme file exists
if [[ ! -f ~/tokyofine.omp.toml ]]; then
	echo "Downloading missing tokyofine.omp.toml..."
	curl -L "https://raw.githubusercontent.com/Hekzory/computerConfiguration/master/linux/ansible/user_home/tokyofine.omp.toml" -o ~/tokyofine.omp.toml
        echo "Theme downloaded successfully."
fi

if [ "$TERM_PROGRAM" != "Apple_Terminal" ]; then
  eval "$(oh-my-posh init zsh --config ~/tokyofine.omp.toml)"
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

# Make new shells get the history lines from all previous
export PROMPT_COMMAND="history -a; $PROMPT_COMMAND"

export FZF_BASE=/usr/share/fzf

# Set personal aliases, overriding those provided by oh-my-zsh libs,
alias make="make -j`nproc`"
alias ninja="ninja -j`nproc`"

alias mirrorupd="sudo reflector --verbose -l 25  --sort rate --save /etc/pacman.d/mirrorlist"

alias please="sudo"

alias cat='bat --style="auto"'
alias ls='lsd -AhlF --color auto --icon auto'
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

# pnpm
export PNPM_HOME="/home/oleg/.local/share/pnpm"
case ":$PATH:" in
  *":$PNPM_HOME:"*) ;;
  *) export PATH="$PNPM_HOME:$PATH" ;;
esac
# pnpm end
