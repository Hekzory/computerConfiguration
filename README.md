# Computer Configuration Scripts
[![ansible-lint](https://github.com/Hekzory/computerConfiguration/actions/workflows/ansible-lint.yml/badge.svg?event=push)](https://github.com/Hekzory/computerConfiguration/actions/workflows/ansible-lint.yml)

Welcome. This repository tries to make my computers behave consistently.

## 🌌 Structure

- `linux/`: Where the penguin dances
  - `ansible/`: Infrastructure as code, because typing commands is so... *manual*
- `windows/`: The glass palace
  - `configuration.dsc.yaml`: Where Windows learns to behave

## 🔮 Usage

1. Clone this: `git clone https://github.com/Hekzory/computerConfiguration.git`
2. Choose your OS:
   - Linux: Navigate to `linux/ansible`
   - Windows: The `configuration.dsc.yaml` awaits your command

## ⚡ CI/CD

The configuration is continuously validated by ansible-lint.

