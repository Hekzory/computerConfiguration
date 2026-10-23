# Opt-in corporate Codex configuration

This role is separate from `codex` and is enabled explicitly through the normal
`run.sh` flow from `linux/ansible/`:

```sh
./run.sh arch-core --corporate
# The same option works with arch-desktop and arch-home.
```

The flag passes `codex_corporate_enabled=true` to the selected playbook. Its
`arch-core` portion applies the base Codex role first, then the corporate role.
Without the flag (or another explicit true value for that variable), the
corporate role is skipped. There is no activation by hostname, user name or
repository origin. Already-installed integrations stay configured when the role
is skipped; this option controls provisioning, not runtime availability.

It manages three corporate MCP configurations, preserving the reviewed 23 read
tools and original server names. The default approval policy remains `prompt`;
only those exact reads use `auto`. The Confluence and VK Workspace deny lists
are retained. Other MCP servers, desktop-generated state, credentials and
`hooks.state` are outside this role's ownership.

The role deploys portable adapters, the `docs-researcher` instructions and two
hook handlers. Hook installation merges with personal handlers instead of
replacing `hooks.json`. No hook trust hash is generated or bypassed. Approve
changed user hooks through the supported client UI if requested. The SessionStart
adapter injects private context only for `gitlab.corp.mail.ru` origins. The
research role inherits its parent model, effort and permissions; its read-only
instruction does not create another sandbox.

Provide these private inputs on each target before running the role:

- `codex_corporate_skill_source` (default `~/.local/share/agent-skills`), containing
  the eight configured corporate skill directories. The personal `yamail` skill
  is preserved. The role creates links under `~/.agents/skills`.
- `codex_corporate_context_source` (default `~/.local/share/agent-context`), with
  `work.md` and `docs-researcher.md`. This can point at a private checkout. Context
  remains private, is copied with mode `0600`, and is never printed in diffs.
- `codex_corporate_mcc_guard_source` (default `~/.claude/hooks/mcc-guard.sh`), the
  reviewed private guard. Its deployed Codex copy no longer depends on Claude's
  installed hook path.
- The existing Confluence MCP runtime at
  `~/.local/share/mcp-servers/node_modules/.bin/confluence-mcp-server`, and a
  private `~/.config/confluence.token` (mode `0600`). This role configures that
  runtime, not npm package versions or credential issuance.

Workspace's header helper reuses only a still-valid matching Claude access token
when present; it does not copy or refresh OAuth state. With no usable cache it
returns `{}` and lets Codex use native authentication. `docs-vk-team` keeps its
existing transport. VPN/access requirements remain external prerequisites.

Private skill contents, work briefs, tokens, npm modules and OAuth state are not
committed here. A machine without these inputs fails before corporate files are
changed. Base defaults may already have been installed by the normal playbook.
Default workstation bootstrap does not apply the corporate role.

On a fresh check-mode run, private assets whose destination directories do not
exist are reported as planned, and the uninstalled hooks helper is skipped.
Prerequisite checks still run. Hook merging is covered by the synthetic tests;
repeat the check after an explicit installation to validate installed helpers.
