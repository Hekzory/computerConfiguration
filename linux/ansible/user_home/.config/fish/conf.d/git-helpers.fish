# git-helpers — aliases + custom functions, auto-loaded from conf.d/
# Loads BEFORE config.fish, so the AI-agent block in config.fish can erase
# the interactive functions below when running under Claude/Cursor.

# Simple aliases — short verbs for common ops
alias g='git'
alias gd='git diff'
alias gpsh='git push'                                       # saving 4 chars, definitely worth it
alias gpll='git pull'
alias gcom='git commit'
alias gfix='git commit --amend'                             # smaller amend
alias gcar='git commit --amend --reset-author --no-edit'    # refresh author/timestamp on last commit
alias gundo='git reset --soft HEAD~1'                       # undo last commit, keep changes

# Destructive — wrapped with confirmation so a stray paste doesn't ruin your evening
function gfuck --description "Hard reset HEAD~1 (discards last commit AND working changes)"
    read -P "Discard last commit AND its working changes? Type 'y': " ans
    test "$ans" = y; or return 1
    git reset --hard HEAD~1
end

function gpshf --description "git push --force (with confirmation)"
    set -l branch (git rev-parse --abbrev-ref HEAD 2>/dev/null)
    test -z "$branch"; and echo "not in a git repo"; and return 1
    read -P "Force-push '$branch' to its upstream? Type 'y': " ans
    test "$ans" = y; or return 1
    git push --force
end

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
