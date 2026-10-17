# Deployed by arch-core from WSL (windows/home in the repo): edit it there, a
# change made here is overwritten on the next run.

# pwsh reads this for -Command and -File runs too, and agents (Claude Code,
# Cursor) drive it that way or through a pipe. Those get a bare shell: no
# banner, no prompt theme, and none of the startup time they cost.
$bare = $env:CLAUDECODE -or $env:CURSOR_TRACE_ID -or [Console]::IsOutputRedirected -or
    [Environment]::GetCommandLineArgs() -match '^[-/]+(c|command|cwa|commandwithargs|ec|encodedcommand|f|file|noni|noninteractive)$'

if (-not $bare) {
    # Same rules as the fish greeting: not in editor terminals or small windows.
    # What it shows is in %APPDATA%\fastfetch\config.jsonc, next to this file in the repo.
    if ((Get-Command fastfetch -ErrorAction Ignore) -and $env:TERM_PROGRAM -ne 'vscode' -and
        $env:TERMINAL_EMULATOR -ne 'JetBrains-JediTerm' -and $Host.UI.RawUI.WindowSize.Height -gt 25) {
        fastfetch
    }

    if (Get-Command oh-my-posh -ErrorAction Ignore) {
        oh-my-posh init pwsh --config "$HOME\tokyofine.omp.toml" | Invoke-Expression
    }
}
Remove-Variable bare
