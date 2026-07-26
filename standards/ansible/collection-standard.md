# Ansible collection standard

Version: 1.0.0

Contract for Ansible collections (future `ansible-collection-generic` golden path).
References [Ansible collection documentation](https://docs.ansible.com/projects/ansible/latest/collections_guide/index.html)
and Galaxy publishing requirements.

## Required layout

```text
.
├── README.md
├── repave.yaml
├── galaxy.yml
├── meta/runtime.yml
├── roles/
│   └── {role_name}/
├── plugins/                   # optional
├── docs/                      # optional
└── changelogs/changelog.yaml  # recommended
```

## `galaxy.yml`

- `namespace` and `name` are immutable after publish.
- `version` follows semantic versioning.
- `readme`, `authors`, `description`, `license`, `tags` required for Galaxy.
- `dependencies` pin collection versions (`namespace.name: "x.y.z"`).
- `repository`, `documentation`, `issues`, `homepage` recommended.

## `meta/runtime.yml`

```yaml
---
requires_ansible: ">=2.15.0"
```

Match the estate minimum Ansible version.

## Role standards within collections

Each role under `roles/` must satisfy [role-standard.md](role-standard.md).
Collection-level ansible-lint runs from the collection root.

## Security

See [security-appendix.md](security-appendix.md). Pin all dependencies in
`galaxy.yml` and document upgrade policy in README.
