#!/usr/bin/env bash

# Set strict mode because we're not savages
set -euo pipefail
IFS=$'\n\t'

# Constants - uppercase by convention
readonly VALID_PLAYBOOKS=("arch-core" "arch-desktop" "arch-home")
readonly REQUIREMENTS_FILE="roles/requirements.yml"

# --- Error Handling: with a hint of theatrical flair ---
die() {
    local msg="$1"
    local code="${2:-1}" # Default to 1 if not provided
    printf "FATAL: %s\n" "$msg" >&2
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

    echo "Installing requirements..."
    if ! ansible-galaxy install -r "$REQUIREMENTS_FILE"; then
        die "Failed to install Ansible requirements"
    fi

    echo "Running playbook..."
    if ! ANSIBLE_STDOUT_CALLBACK=debug ansible-playbook -v --ask-become-pass "$PLAYBOOK_FILE"; then
        die "Playbook execution failed"
    fi

    echo "Playbook executed successfully"
}

# Execute main function
main
