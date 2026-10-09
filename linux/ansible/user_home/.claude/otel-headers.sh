#!/bin/bash
# otelHeadersHelper for Claude Code: prints the auth header of the metrics
# endpoint as JSON. Claude Code runs it at startup and every ~29 minutes.
#
# The token is the only secret of the setup and lives on this machine alone, in
# ~/.claude/otel-token (0600). It never reaches git, the world-readable policy
# file or the environment that Claude's commands inherit.
token=$(tr -d '[:space:]' < "$HOME/.claude/otel-token") || exit 1
[ -n "$token" ] || exit 1
printf '{"Authorization":"Bearer %s"}\n' "$token"
