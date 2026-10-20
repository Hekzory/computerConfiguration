#!/usr/bin/env python3
"""PreToolUse guard: a long run gets its time limit before it starts.

Benchmarks, stress tests and subagents that keep going for an hour on a fix that
needed minutes are the most common way an agent session goes wrong here. Picking a
limit up front is the one decision that prevents it, so it is enforced, not asked for:
- Bash: a test or benchmark runner, or anything started in the background, carries
  `timeout` (coreutils). A foreground command is capped by the tool itself anyway;
  CI watchers (`gh run watch`, `gh pr checks --watch`) end when the CI run does.
- Agent: the brief names a wall-clock budget.

Runners count only at command position, so `grep 'cargo test' ci.yml` passes, and a
heredoc's body counts only when a shell runs it (`ssh host bash -s <<EOF`), not when
it is a file being written or a script fed to python.
"""
import json
import re
import sys

# start of a command: line start, after ; & | ( or $(, then optional VAR=x, sudo, env,
# nice, time, or an interpreter (bash bench.sh, python3 bench.py)
AT_CMD = r"(?:^|[;&|(]|\$\()[ \t]*(?:(?:[A-Za-z_]\w*=\S*|sudo|env|nice|ionice|time|exec|bash|sh|python3?)[ \t]+)*"
RUNNERS = (
    r"(?:(?:\./)?gradlew|gradle)[ \t][^;&|\n]*\b(?:test|check|jacoco)"
    r"|ctest|cargo[ \t]+(?:\+\S+[ \t]+)?(?:test|bench|nextest)|hyperfine"
    r"|pytest|python3?[ \t]+-m[ \t]+pytest|(?:npx[ \t]+)?vitest|node[ \t][^;&|\n]*run-vitest"
    r"|(?:npm|pnpm|yarn)[ \t]+(?:run[ \t]+)?test|make[ \t](?:[^;&|\n]*[ \t])?(?:test|check|bench)"
    r"|go[ \t]+test|[^\s;&|]*(?:bench|stress)[^\s;&|/]*\.(?:sh|py)|stress-ng"
)
RUNNER = re.compile(AT_CMD + "(?:" + RUNNERS + r")(?=\s|$)", re.M)
OFFSCREEN = re.compile(r"(?:^|\s)--offscreen(?=[\s=]|$)", re.M)  # DevTale's benchmark mode
TIMEOUT = re.compile(r"(?:^|[^\w-])timeout\s")
CI_WATCH = re.compile(r"gh\s+(?:run\s+watch|pr\s+checks\s[^;&|\n]*--watch)")
BUDGET = re.compile(r"budget|wall[- ]?clock|time limit|бюджет|лимит времени", re.I)
HEREDOC = re.compile(r"<<-?[ \t]*(['\"]?)([A-Za-z_]\w*)\1")
SHELL_RUNS_IT = re.compile(r"(?:^|[\s;&|(])(?:bash|sh|zsh|ssh)(?=\s|$)")


def drop_inert_heredocs(cmd):
    out, lines, i = [], cmd.split("\n"), 0
    while i < len(lines):
        line = lines[i]
        out.append(line)
        i += 1
        m = HEREDOC.search(line)
        if not m:
            continue
        keep = bool(SHELL_RUNS_IT.search(line[: m.start()]))
        while i < len(lines) and lines[i].strip() != m.group(2):
            if keep:
                out.append(lines[i])
            i += 1
        i += 1  # the delimiter line
    return "\n".join(out)


def deny(reason):
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny", "permissionDecisionReason": reason}}))
    sys.exit(0)


try:
    event = json.load(sys.stdin)
except ValueError:
    sys.exit(0)
tool = event.get("tool_name")
args = event.get("tool_input") or {}

if tool == "Bash":
    cmd = args.get("command") or ""
    if TIMEOUT.search(cmd):
        sys.exit(0)
    live = drop_inert_heredocs(cmd)
    if RUNNER.search(live) or OFFSCREEN.search(live):
        deny(
            "Time limit first: start this run as `timeout <N> …`, N sized to what the answer is worth "
            "(a unit test run: a few minutes; a benchmark: the shortest run that answers the question). "
            "No test, benchmark or stress run without a limit chosen up front."
        )
    if args.get("run_in_background") and not CI_WATCH.search(cmd):
        deny(
            "Background job without a time limit: start it as `timeout <N> …` (a server that has to stay up: "
            "`timeout 2h …`). CI watchers (gh run watch, gh pr checks --watch) are exempt."
        )
elif tool == "Agent":
    if not BUDGET.search(args.get("prompt") or ""):
        deny(
            'Subagent brief without a time budget: add a line such as "Budget: about 20 minutes wall-clock; '
            'tests once per commit, no extra benchmark runs." Every subagent is time-boxed.'
        )
sys.exit(0)
