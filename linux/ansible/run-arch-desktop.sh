#!/bin/bash

ansible-galaxy install -r requirements.yml
ANSIBLE_STDOUT_CALLBACK=debug ansible-playbook -v --ask-become-pass arch-desktop.yml
