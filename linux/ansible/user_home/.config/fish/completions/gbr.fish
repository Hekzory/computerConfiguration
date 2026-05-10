# Completions for `gbr` (defined in conf.d/git-helpers.fish)
# Positional arg is a NEW branch name — no candidates suggested.

complete -c gbr -f
complete -c gbr -s h -l help -d 'Show help'
complete -c gbr -s l -l list -d 'List branch types'
complete -c gbr -s b -l base -x \
    -a "(git for-each-ref --format='%(refname:short)' refs/heads/ 2>/dev/null)" \
    -d 'Base branch (default: master)'
