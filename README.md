# Computer Configuration Scripts

[![ansible-lint](https://github.com/Hekzory/computerConfiguration/actions/workflows/ansible-lint.yml/badge.svg?event=push)](https://github.com/Hekzory/computerConfiguration/actions/workflows/ansible-lint.yml)

Welcome. This repository tries to make my computers behave consistently.

## 🌌 Structure

- `linux/`: Where the penguin is stored
    - `ansible/`: Infrastructure as code
- `windows/`: The glass palace
    - `configuration.dsc.yaml`: trying out declarative configuration by windows standards

## 🔮 Usage

1. Clone this: `git clone https://github.com/Hekzory/computerConfiguration.git`
2. Choose your OS:
    - Linux: Navigate to `linux/ansible`
    - Windows: The `configuration.dsc.yaml` awaits your command

## ⚡ CI/CD

The configuration is continuously validated by ansible-lint.
