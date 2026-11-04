#!/usr/bin/env python3
"""PreToolUse guard: bash syntax sent over ssh to a fish login shell.

arch-core makes fish the login shell on every machine it sets up, and sshd hands a
remote command to the login shell. So `ssh host 'f=/x; for i in 1 2; do …; done'`
dies in fish ("Unsupported use of '='", "'else' builtin not inside of if block"), and
so does a script piped in with `ssh host <<EOF`. This denies those with the fix:
send the script to bash explicitly. A remote command without bash-only syntax, or one
that already starts with bash/sh, passes untouched.
"""
import json
import re
import shlex
import sys

HEREDOC = re.compile(r"<<-?[ \t]*(['\"]?)([A-Za-z_]\w*)\1")
# a word allowed between the start of a command and `ssh`
PREFIX = re.compile(r"^(?:timeout|sudo|env|nice|nohup|exec|time|ionice|-\S+|\d+(?:\.\d+)?[smhd]?|[A-Za-z_]\w*=\S*)$")
SEPARATORS = {";", "&", "&&", "|", "||", "(", ")", "\n"}
# ssh options that take a value
WITH_ARG = set("BbcDEeFIiJLlmOoPpQRSWw")
# checked outside quotes; fish takes `VAR=x cmd` but not a bare `VAR=x;` or `x=$(…)`
BASH_ONLY = re.compile(
    r";\s*(?:do|then)\b|\besac\b|\$\(\(|\$\{|`|\[\[|\$\?|<<"
    r"|(?:^|[;&|]\s*)(?:[A-Za-z_]\w*=\S*\s*(?:$|;|&&|\|\|)|[A-Za-z_]\w*=\$\(|\$\()"
)
# fish expands $ inside double quotes too, and these forms don't exist there
IN_DOUBLE_QUOTES = re.compile(r"\$\{|\$\(\(|\$\?")
SHELLS = {"bash", "sh", "zsh", "dash"}


def strip_heredoc_bodies(cmd):
    """Drop the bodies of heredocs opened outside quotes; `<<` inside a quoted remote
    command belongs to that command and stays."""
    out, lines, i, quote = [], cmd.split("\n"), 0, None
    while i < len(lines):
        line = lines[i]
        out.append(line)
        i += 1
        bare = []
        for ch in line:
            if quote:
                if ch == quote:
                    quote = None
                bare.append(" ")
            elif ch in "'\"":
                quote = ch
                bare.append(" ")
            else:
                bare.append(ch)
        m = None if quote else HEREDOC.search(line) if HEREDOC.search("".join(bare)) else None
        if m:
            while i < len(lines) and lines[i].strip() != m.group(2):
                i += 1
            i += 1
    return "\n".join(out)


def unquoted_newlines_to_semicolons(cmd):
    out, quote, esc = [], None, False
    for ch in cmd:
        if esc:
            esc = False
        elif ch == "\\" and quote != "'":
            esc = True
        elif quote:
            if ch == quote:
                quote = None
        elif ch in "'\"":
            quote = ch
        elif ch == "\n":
            ch = " ; "
        out.append(ch)
    return "".join(out)


def split_quotes(text):
    """Text outside quotes (newlines as ;) and the contents of double-quoted parts."""
    outside, dq, quote, cur = [], [], None, []
    for ch in text:
        if quote:
            if ch == quote:
                if quote == '"':
                    dq.append("".join(cur))
                quote, cur = None, []
            else:
                cur.append(ch)
        elif ch in "'\"":
            quote = ch
            outside.append(" ")
        else:
            outside.append(";" if ch == "\n" else ch)
    return "".join(outside), dq


def problem(cmd):
    text = unquoted_newlines_to_semicolons(strip_heredoc_bodies(cmd))
    lex = shlex.shlex(text, posix=True, punctuation_chars=True)
    lex.whitespace_split = True
    tokens = list(lex)
    for i, tok in enumerate(tokens):
        if tok != "ssh" and not tok.endswith("/ssh"):
            continue
        j = i - 1
        while j >= 0 and tokens[j] not in SEPARATORS and PREFIX.match(tokens[j]):
            j -= 1
        if j >= 0 and tokens[j] not in SEPARATORS:
            continue  # ssh is an argument here (grep ssh, man ssh …), not the command
        k = i + 1
        while k < len(tokens) and tokens[k].startswith("-") and len(tokens[k]) > 1:
            k += 2 if tokens[k][-1] in WITH_ARG and len(tokens[k]) == 2 else 1
        k += 1  # the host
        rest, stdin_script = [], False
        while k < len(tokens) and tokens[k] not in SEPARATORS:
            if tokens[k].startswith("<<"):
                stdin_script = True
                break
            if tokens[k][0] in "<>" or re.match(r"^\d*[<>]", tokens[k]):
                break
            rest.append(tokens[k])
            k += 1
        remote = " ".join(rest)
        first = remote.split()[0] if remote.split() else ""
        if first in SHELLS or first.endswith("/bash"):
            continue
        if not remote and stdin_script:
            return "a heredoc piped to `ssh host` runs in the remote login shell, which is fish"
        outside, dq = split_quotes(remote)
        if remote and (BASH_ONLY.search(outside) or any(IN_DOUBLE_QUOTES.search(q) for q in dq)):
            return "the remote command uses bash syntax, and the remote login shell is fish"
    return None


try:
    event = json.load(sys.stdin)
    if event.get("tool_name") != "Bash":
        sys.exit(0)
    why = problem((event.get("tool_input") or {}).get("command") or "")
except (ValueError, AttributeError):
    sys.exit(0)  # unparsable input: let it through
if why:
    reason = (
        f"Not sent: {why}. Hand the script to bash explicitly: `ssh host bash -s <<'EOF'` … `EOF` "
        "(add `-T` and `</dev/null` to docker compose exec inside it), or `ssh host bash -c '…'`."
    )
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny", "permissionDecisionReason": reason}}))
sys.exit(0)
