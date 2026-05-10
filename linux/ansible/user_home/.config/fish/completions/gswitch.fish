# Completions for `gswitch` (defined in conf.d/git-helpers.fish)
# Positional arg is an EXISTING local branch — suggest from refs/heads.

complete -c gswitch -f
complete -c gswitch -s h -l help -d 'Show help'
complete -c gswitch -s l -l list -d 'List branches'
complete -c gswitch \
    -a "(git for-each-ref --format='%(refname:short)' refs/heads/ 2>/dev/null)" \
    -d Branch
