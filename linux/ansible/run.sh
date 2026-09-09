#!/usr/bin/env bash

# Set strict mode because we're not savages
set -euo pipefail
IFS=$'\n\t'

# Constants - uppercase by convention
readonly VALID_PLAYBOOKS=("arch-core" "arch-desktop" "arch-home")
readonly REQUIREMENTS_FILE="roles/requirements.yml"
sudo_refresh_pid=""

# Colors for better output
readonly GREEN='\033[0;32m'
readonly RED='\033[0;31m'
readonly YELLOW='\033[0;33m'
readonly BLUE='\033[0;34m'
readonly NC='\033[0m' # No Color

# --- Error Handling: with a hint of theatrical flair ---
die() {
    local msg="$1"
    local code="${2:-1}" # Default to 1 if not provided
    printf '%sFATAL: %s%s\n' "$RED" "$msg" "$NC" >&2
    exit "$code"
}

# Function to display usage
show_usage() {
    cat <<EOF
Usage: $(basename "$0") <playbook>
Available playbooks: ${VALID_PLAYBOOKS[*]}
EOF
    exit 1
}

# Check if exactly one argument is provided
[[ $# -ne 1 ]] && show_usage

# Validate playbook argument using array
playbook_valid=0
for valid_playbook in "${VALID_PLAYBOOKS[@]}"; do
    if [[ "$1" == "$valid_playbook" ]]; then
        playbook_valid=1
        break
    fi
done

[[ $playbook_valid -eq 0 ]] && die "Invalid playbook specified: $1"

# Set the PLAYBOOK variable
readonly PLAYBOOK_FILE="$1.yml"

# Function to check if files exist
check_files_exist() {
    local file
    for file in "$@"; do
        [[ -f "$file" ]] || die "File not found: $file"
    done
}

# Function to check command availability
check_command() {
    command -v "$1" >/dev/null 2>&1 || die "$1 is not installed"
}

# Main execution
main() {
    # Check dependencies
    check_files_exist "$PLAYBOOK_FILE" "$REQUIREMENTS_FILE"
    check_command ansible-galaxy
    check_command ansible-playbook

    # Authenticate once up front (fingerprint or password) and keep the sudo
    # ticket alive in the background. Ansible then runs plain `sudo -n`, which
    # never touches PAM -- with pam_fprintd in the sudo stack, every become
    # task would otherwise sit waiting for a finger.
    sudo -v || die "sudo authentication failed"
    ( while sudo -n -v 2>/dev/null; do sleep 60; done ) &
    sudo_refresh_pid=$!

    printf '%sInstalling requirements...%s\n' "$BLUE" "$NC"
    if ! ansible-galaxy install -r "$REQUIREMENTS_FILE"; then
        die "Failed to install Ansible requirements"
    fi

    echo "Running playbook..."
    if ! ANSIBLE_STDOUT_CALLBACK=debug ansible-playbook -v "$PLAYBOOK_FILE"; then
        die "Playbook execution failed"
    fi

    printf '%sPlaybook executed successfully%s\n' "$GREEN" "$NC"
}

# Trap ctrl-c and call cleanup
trap 'echo -e "${YELLOW}Exiting...${NC}"; exit 130' INT
trap 'kill "$sudo_refresh_pid" 2>/dev/null || true' EXIT

# Execute main function
main
