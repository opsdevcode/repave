# Ansible role standard

Version: 1.0.0

Authoritative role contract for the `ansible-role-generic` golden path. Combines
[Ansible role structure](https://docs.ansible.com/projects/ansible/latest/playbook_guide/playbooks_reuse_roles.html),
Galaxy metadata requirements, ansible-lint **production** profile expectations,
and repave security appendix rules.

## Design principles

1. **Idempotent and explicit.** Every task has a descriptive `name`; privilege
   escalation uses explicit `become`.
2. **FQCN everywhere.** Use fully qualified collection names (`ansible.builtin.*`).
3. **Single entry point.** `tasks/main.yml` imports focused task files; do not
   scatter entry points across the role tree.
4. **Secure defaults.** No secrets in git; sensitive tasks use `no_log`.
5. **Testable.** Molecule scenario under `molecule/default/` with converge and verify.

## Required layout

```text
.
├── README.md
├── repave.yaml
├── .ansible-lint              # copied from repave ansible-lint pack
├── .yamllint
├── meta/
│   ├── main.yml               # Galaxy metadata
│   └── argument_specs.yml     # role argument schema
├── defaults/main.yml
├── vars/                      # optional internal vars
├── tasks/
│   ├── main.yml               # single entry — import_tasks only
│   └── run.yml                # implementation tasks
├── handlers/main.yml
└── molecule/default/
    ├── molecule.yml
    ├── converge.yml
    └── verify.yml
```

## Galaxy metadata (`meta/main.yml`)

Required `galaxy_info` fields:

- `standalone: true`
- `role_name`, `namespace`, `author`, `description`, `license`
- `min_ansible_version` (match blueprint input)
- `platforms` (from blueprint `target_platforms`)
- `galaxy_tags` (lowercase alphanumeric, max 20 tags)

Do not use placeholder values (`your name`, `your description`). Pin
`dependencies` only when required; prefer explicit playbook role lists for
optional composition.

## Task conventions

- Use `ansible.builtin.import_tasks` / `include_tasks` from `tasks/main.yml`.
- Prefer `loop` over deprecated `with_*` forms.
- Avoid bare `command` / `shell` without `creates`, `removes`, or `changed_when`.
- Do not use dot notation for dictionary keys; use bracket notation where required
  by ansible-lint production rules.

## Security (see security-appendix.md)

- No credential literals in tasks, defaults, or vars.
- `no_log: true` on tasks handling passwords, tokens, or private keys.
- Explicit file modes on `copy`, `template`, and `file` tasks.

## Testing

- Molecule `default` scenario with Docker driver (or documented alternative).
- `converge.yml` applies the role; `verify.yml` asserts expected state.
- All gates in the blueprint must pass before publish.

## Exceptions

Document standard exceptions in the role README and list them in
`.ansible-lint-ignore` with rule id and rationale.
