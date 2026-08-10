#!/bin/bash
# Claude Code statusline: model · effort · context % (k tokens) · current dir
# Field names differ between releases, hence the `//` fallback chains — an older
# CLI that lacks .context_window just drops that segment instead of printing null.
input=$(cat)

model=$(printf '%s' "$input" | jq -r '.model.display_name // .model.id // "?"')
effort=$(printf '%s' "$input" | jq -r '.effort.level // .effort_level // empty')
dir=$(printf '%s' "$input" | jq -r '.workspace.current_dir // .cwd // empty')
tokens=$(printf '%s' "$input" | jq -r '.context_window.total_input_tokens // empty' | cut -d. -f1)
pct=$(printf '%s' "$input" | jq -r '
  (.context_window.used_percentage
   // (if (.context_window.total_input_tokens // 0) > 0 and (.context_window.context_window_size // 0) > 0
       then (.context_window.total_input_tokens / .context_window.context_window_size * 100)
       else empty end)
   // empty)' | cut -d. -f1)

out="$model"
[ -n "$effort" ] && out="$out · $effort"
if [ -n "$pct" ]; then
  if   [ "$pct" -ge 80 ]; then col=$'\033[31m'   # red
  elif [ "$pct" -ge 60 ]; then col=$'\033[33m'   # yellow
  else                         col=$'\033[32m'   # green
  fi
  tokstr=""
  if [ -n "$tokens" ] && [ "$tokens" -gt 0 ] 2>/dev/null; then
    if [ "$tokens" -ge 1000000 ]; then
      tokstr=" ($(awk "BEGIN{printf \"%.2fM\", $tokens/1000000}"))"
    else
      tokstr=" ($(( (tokens + 500) / 1000 ))k)"
    fi
  fi
  out="$out · ${col}ctx ${pct}%${tokstr}$(printf '\033[0m')"
fi
if [ -n "$dir" ]; then
  dir=${dir/#$HOME/\~}
  out="$out · $(printf '\033[2m')$dir$(printf '\033[0m')"
fi
printf '%s\n' "$out"
