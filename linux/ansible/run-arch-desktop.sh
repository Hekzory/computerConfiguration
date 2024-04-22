#!/bin/bash

ansible-galaxy install -r requirements.yml
ansible-playbook -v --ask-become-pass arch-desktop.yml
