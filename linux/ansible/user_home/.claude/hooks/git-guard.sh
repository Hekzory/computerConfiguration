#!/bin/bash
# PreToolUse guard: denies `git commit` carrying AI attribution
# (Co-Authored-By, "Generated with Claude", noreply@anthropic.com, robot emoji).
#
# Belt and braces on top of the empty `attribution` in managed settings: that one
# stops Claude Code from appending trailers on its own, this one catches a message
# that picked them up anyway — pasted, amended, or copied from another commit.

input=$(cat)
cmd=$(printf '%s' "$input" | jq -r '.tool_input.command // empty' 2>/dev/null)

# only git commit is interesting; anything else passes through untouched
printf '%s' "$cmd" | grep -qE 'git[[:space:]]+([a-z-]+[[:space:]]+)*commit' || exit 0

if printf '%s' "$cmd" | grep -qiE 'co-authored-by|generated with.*claude|noreply@anthropic\.com|🤖'; then
  cat <<'EOF'
{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"Политика: никаких Co-Authored-By / упоминаний Claude в коммитах. Перепиши сообщение коммита без AI-атрибуции."}}
EOF
  exit 0
fi
exit 0
