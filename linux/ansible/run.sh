#!/bin/bash

# Function to display an error message and exit
function echo_error() {
    echo "Error: $1" 1>&2
    exit 1
}

# Check if exactly one argument is provided
[ "$#" -ne 1 ] && echo_error "No playbook specified or wrong argument count. Please specify 'arch-core' or 'arch-desktop'."

# Set the PLAYBOOK variable based on the argument
case "$1" in
    arch-core|arch-desktop)
        PLAYBOOK_FILE="$1.yml" ;;
    *)
        echo_error "Error: Invalid playbook specified: $1. Please specify 'arch-core' or 'arch-desktop'." ;;
esac

# Function to check if files exist
check_files_exist() {
    for file in "$@"; do
        if [ ! -f "$file" ]; then
            echo_error "Error: File is needed, but not found: $file"
        fi
    done
}

# Check if needed files exist
check_files_exist "$PLAYBOOK_FILE" "requirements.yml"

# Function to check Ansible and Ansible Galaxy
check_ansible_tools() {
    local tools=("ansible-galaxy" "ansible-playbook")
    for tool in "${tools[@]}"; do
      if ! [ -x "$(command -v "$tool")" ]; then
        echo_error "$tool command is not installed. Install it first."
      fi
    done
}

check_ansible_tools

echo "Installing requirements..."
ansible-galaxy install -r "requirements.yml"

echo "Running playbook..."
ANSIBLE_STDOUT_CALLBACK=debug ansible-playbook -v --ask-become-pass "$PLAYBOOK_FILE"

echo "Playbook executed successfully."
