#!/bin/bash
# Codex PreToolUse guard: same no-attribution policy as the Claude guard, extended
# to Codex/OpenAI/ChatGPT. Claude's original hook and settings stay untouched.
# This checks command text, not arbitrary scripts or the final Git object.

input=$(cat)
cmd=$(printf '%s' "$input" | jq -r 'select(.tool_name == "Bash") | .tool_input.command // empty' 2>/dev/null)

# Accept git's global options (-C, -c, --git-dir, etc.) before the subcommand.
# Keep shell separators out of that prefix so a later command is not a subcommand.
printf '%s' "$cmd" | grep -qE '(^|[[:space:]/])git[[:space:]]+([^;&|]*[[:space:]])?commit([[:space:]]|$)' || exit 0

if printf '%s' "$cmd" | grep -qiE 'co-authored-by|generated (with|by|using).*(claude|codex|chatgpt|openai)|(noreply|codex|claude|chatgpt)@(anthropic|openai)\.com|🤖'; then
  cat <<'JSON'
{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"No AI attribution in commits. Remove Co-Authored-By and AI-generated trailers, then retry."}}
JSON
fi
exit 0
