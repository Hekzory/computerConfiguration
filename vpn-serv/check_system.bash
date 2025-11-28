#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
# sysctl-check.sh
# Compare desired values in 99-vpn-performance.conf
# against currently active kernel values.
# Does NOT apply anything — read-only check.
# ─────────────────────────────────────────────────────────────

set -euo pipefail

#CONF="/etc/sysctl.d/99-vpn-performance.conf"
CONF="99-sysctl-perf.conf"

# ── Colors ──
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
RESET='\033[0m'

if [[ ! -f "$CONF" ]]; then
    echo -e "${RED}Error:${RESET} $CONF not found."
    exit 1
fi

# ── Column widths ──
W_KEY=58
W_DESIRED=28
W_CURRENT=28
W_STATUS=10

# ── Header ──
echo ""
echo -e "${BOLD}$(printf "%-${W_KEY}s %-${W_DESIRED}s %-${W_CURRENT}s %-${W_STATUS}s" \
    "PARAMETER" "DESIRED" "CURRENT" "STATUS")${RESET}"
printf '%.0s─' $(seq 1 $((W_KEY + W_DESIRED + W_CURRENT + W_STATUS)))
echo ""

# ── Counters ──
total=0
match=0
mismatch=0
missing=0

# ── Parse and compare ──
while IFS= read -r line; do
    # Strip inline comments and leading/trailing whitespace
    line="${line%%#*}"
    line="$(echo "$line" | xargs 2>/dev/null || true)"

    # Skip empty lines
    [[ -z "$line" ]] && continue

    # Must contain '=' to be a valid key=value pair
    [[ "$line" != *"="* ]] && continue

    # Split into key and desired value
    key="$(echo "$line" | cut -d'=' -f1 | xargs)"
    desired="$(echo "$line" | cut -d'=' -f2- | xargs)"

    ((total++)) || true

    # Attempt to read current kernel value
    if current="$(sysctl -n "$key" 2>/dev/null)"; then
        # Normalize whitespace (kernel may use tabs between values)
        current_norm="$(echo "$current" | xargs)"
        desired_norm="$(echo "$desired" | xargs)"

        if [[ "$current_norm" == "$desired_norm" ]]; then
            status="${GREEN}OK${RESET}"
            ((match++)) || true
        else
            status="${RED}MISMATCH${RESET}"
            ((mismatch++)) || true
        fi
    else
        current_norm="(not found)"
        status="${YELLOW}MISSING${RESET}"
        ((missing++)) || true
    fi

    printf "%-${W_KEY}s %-${W_DESIRED}s %-${W_CURRENT}s " \
        "$key" "$desired_norm" "$current_norm"
    echo -e "$status"

done <"$CONF"

# ── Summary ──
echo ""
printf '%.0s─' $(seq 1 $((W_KEY + W_DESIRED + W_CURRENT + W_STATUS)))
echo ""
echo -e "${BOLD}Total:${RESET} $total   " \
    "${GREEN}OK:${RESET} $match   " \
    "${RED}Mismatch:${RESET} $mismatch   " \
    "${YELLOW}Missing:${RESET} $missing"
echo ""

if [[ $mismatch -gt 0 || $missing -gt 0 ]]; then
    echo -e "${CYAN}To apply all desired values:${RESET}"
    echo "  sudo sysctl --system"
    echo ""
    if [[ $missing -gt 0 ]]; then
        echo -e "${YELLOW}Note:${RESET} 'MISSING' usually means a kernel module is not loaded."
        echo "  e.g.:  sudo modprobe nf_conntrack"
        echo ""
    fi
fi
