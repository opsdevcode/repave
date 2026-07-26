# Ansible playbook / project standard

Version: 1.0.0

Contract for playbook projects (future `ansible-playbook-project-generic` golden
path). Synthesizes Ansible project layout guidance and production-profile lint
expectations.

## Recommended layout

```text
.
├── README.md
├── repave.yaml
├── ansible.cfg                # optional; roles_path, inventory defaults
├── site.yml                   # or playbooks/site.yml
├── requirements.yml           # pinned roles and collections
├── inventories/
│   ├── dev/
│   │   └── hosts.yml
│   └── prod/
│       └── hosts.yml
├── group_vars/
│   └── all/
│       └── vars.yml
├── host_vars/
├── roles/                     # optional local roles
└── collections/               # optional local collections
```

## Playbook conventions

- Entry playbooks use FQCN for modules and roles.
- Prefer `roles:` or `ansible.builtin.import_role` with explicit names.
- Limit privilege escalation; document required `become` in README.
- No secrets in plain YAML — use Ansible Vault or external secret stores.

## Inventory safety

- Separate dev/stage/prod inventories.
- Do not commit production credentials.
- Vault-encrypted files use `.vault.yml` suffix and documented password workflow.

## Dependencies

`requirements.yml` must pin versions:

```yaml
---
roles:
  - name: namespace.role_name
    version: "1.2.3"
collections:
  - name: namespace.collection_name
    version: "2.0.0"
```

## Testing

- Molecule or ansible-test integration for critical playbooks.
- ansible-lint on project root with production profile.

## Security

See [security-appendix.md](security-appendix.md).
