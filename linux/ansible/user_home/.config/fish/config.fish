# Initializing some environment variables earlier:
set -gx EDITOR nvim
set -gx PAGER less
set -gx MANROFFOPT "-c"
set -gx MANPAGER "sh -c 'col -bx | bat -l man -p'"

function fish_greeting
    if test (tput colors) -ge 256; and test (tput lines) -gt 25
    	fastfetch
    else
        echo "Welcome. Small screen or low color support detected, will not display fastfetch."
    end
end

if test (tput colors) -lt 256
    set -gx LOW_COLOR_SUPPORT 1
end

# Theme handling with error checking
set -g theme_path ~/tokyofine.omp.toml
if not test -f $theme_path
    echo "🔄 Downloading missing theme..."
    curl -sL "https://raw.githubusercontent.com/Hekzory/computerConfiguration/master/linux/ansible/user_home/tokyofine.omp.toml" -o $theme_path || echo "❌ Theme download failed!"
end

# Initialize oh-my-posh if available
type -q oh-my-posh && oh-my-posh init fish --config $theme_path | source

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

#   For when 'sudo' is too mainstream
alias please='echo "Oh, 𝓿𝓮𝓻𝔂 well..." && sudo' 

if type -q bat
    alias cat='bat --style=auto'
end
if type -q eza
    alias ls='eza -Ahl --color=auto --icons=auto'
end
alias rm='rm -i'
alias cp='cp -i'
alias mv='mv -i'
alias less='less -R'
if type -q rg
    alias grep='rg -u'
end
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

# git part
alias g='git'
alias gundo='git reset --soft HEAD~1'  # Undo last commit, keep changes
alias gfuck='git reset --hard HEAD~1'  # Nuclear option: undo last commit and changes
alias gcar='git commit --amend --reset-author --no-edit' # Update last commit time signature and author
alias gfix='git commit --amend' # smaller amend command
alias gpshf='git push --force' # no comments
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
set -gx PNPM_HOME "$HOME/.local/share/pnpm"
if not string match -q -- $PNPM_HOME $PATH
  set -gx PATH "$PNPM_HOME" $PATH
end
# pnpm end



function gbr --description "Create and checkout a new branch with useful functionality"
    set -l source_branch "master"

    argparse --name=gbr 'h/help' 'l/list' 'b/base=' -- $argv
    or return

    if set -q _flag_help
        echo "Usage: gbr [-b/--base BASE_BRANCH] BRANCH_NAME"
        echo "Creates a new branch with useful functionality"
        echo ""
        echo "Options:"
        echo "  -h/--help          Show this help message"
        echo "  -l/--list          List available branch types"
        echo "  -b/--base BRANCH   Specify base branch (defaults to master, obviously)"
        echo ""
        echo "Examples:"
        echo "  gbr add-login-page"
        echo "  gbr -b production critical-error"
        return 0
    end

    # Set base branch
    if set -q _flag_base
        set source_branch $_flag_base
    end

    # Check if branch name is provided
    if test (count $argv) -eq 0
        echo "Error: Branch name is required"
        return 1
    end

    # Construct branch name
    set -l branch_name "$argv[1]"

	# Check for uncommitted changes
    set -l has_changes (git status --porcelain)
    set -l stash_created false

	if test -n "$has_changes"
        echo "📦 Uncommitted changes. Stashing them..."
        git stash push -m "auto-stash before switching branch"
        set stash_created true
	end

    # Check if we're already on the source branch
    set -l current_branch (git rev-parse --abbrev-ref HEAD)
    if test $current_branch != $source_branch
        echo "Switching to $source_branch..."
        git checkout $source_branch
        or begin
            if test $stash_created = true
                echo "Well, that failed spectacularly. Bringing your changes back..."
                git stash pop
            end
            return 1
		end
	end

    # Update source branch
    echo "Updating $source_branch..."
    git pull origin $source_branch --rebase
    or begin
        if test $stash_created = true
            echo "That didn't work. Rolling back..."
            git stash pop
		end
        return 1
    end

    # Create and checkout new branch
    echo "Creating new branch: $branch_name"
    git checkout -b $branch_name

    # Set upstream
    echo "Setting upstream branch..."
    git push --set-upstream origin $branch_name

    echo "🎉 Successfully created and checked out $branch_name based on $source_branch."
    if test $stash_created = true
        echo "📦 Stash was created during branch creation, unstashing."
		git stash pop
    end
end

function gswitch --description "Switch branches without losing your mind or your changes"
    argparse --name=gswitch 'h/help' 'l/list' -- $argv
    or return

    if set -q _flag_help
        echo "gswitch [branch_name]"
        echo ""
        echo "Options:"
        echo "  -h/--help    Show this explanation"
        echo "  -l/--list    List available branches"
        echo ""
        echo "Examples (because apparently we need those):"
        echo "  gswitch feature-login"
        echo "  gswitch master"
        return 0
    end

    if set -q _flag_list
        echo "Here are all your branches:"
        git branch --sort=-committerdate | string replace --regex '^\*?\s*' ''
        return 0
    end

    if test (count $argv) -eq 0
        echo "You want to switch branches but don't tell which one?"
        echo "Try 'gswitch --list'."
        return 1
    end

    set -l target_branch $argv[1]

    # Check if the branch exists
    if not git show-ref --verify --quiet refs/heads/$target_branch
        echo "Branch '$target_branch' doesn't exist."
        echo "Here's what you actually have:"
        git branch --sort=-committerdate | string replace --regex '^\*?\s*' ''
        return 1
    end

    # Check if we're already on the target branch
    set -l current_branch (git rev-parse --abbrev-ref HEAD)
    if test $current_branch = $target_branch
        echo "You're already on '$target_branch'. Task failed successfully?"
        return 0
    end

    # Check for uncommitted changes
    set -l has_changes (git status --porcelain)
    set -l stash_created false

    if test -n "$has_changes"
        echo "Oh look, uncommitted changes. Let's save those before we lose them..."
        git stash push -m "auto-stash before switching to $target_branch"
        or begin
            echo "Failed to stash changes. Maybe commit them yourself next time?"
            return 1
        end
        set stash_created true
    end

    echo "Switching to '$target_branch'..."
    git checkout $target_branch
    or begin
        if test $stash_created = true
            echo "Well, that didn't work. Bringing your changes back..."
            git stash pop
        end
        return 1
    end

    # Update branch if it's not master/main
    if test $target_branch != "master" -a $target_branch != "main"
        echo "Checking for updates... because your branch is probably behind."
        git pull --rebase origin $target_branch
        or echo "Couldn't update the branch. You're on your own with this one."
    end

    if test $stash_created = true
        echo "Restoring your uncommitted changes."
        git stash pop
        or begin
            echo "Failed to restore changes. They're probably still in stash. Good luck."
            echo "Use 'git stash list' to find them."
            return 1
        end
    end

    echo "You're on '$target_branch' now."
end
