# Ansible standards (repave)

Versioned Ansible configuration-management standards for repave golden paths.

| Document | Version | Scope |
| --- | --- | --- |
| [role-standard.md](role-standard.md) | 1.0.0 | Galaxy-compatible roles |
| [collection-standard.md](collection-standard.md) | 1.0.0 | Ansible collections |
| [playbook-project-standard.md](playbook-project-standard.md) | 1.0.0 | Playbook / inventory projects |
| [security-appendix.md](security-appendix.md) | 1.0.0 | Cross-cutting security rules |

Blueprints pin `spec.standard.source: examples/standards/ansible` and
`spec.standard.version`. The enforceable policy pack lives at
`examples/ansible-lint/pack/` (pinned separately via `spec.ansible_lint`).

Sources synthesized: [Ansible role documentation](https://docs.ansible.com/projects/ansible/latest/playbook_guide/playbooks_reuse_roles.html),
Galaxy metadata requirements, ansible-lint `production` and `safety` profiles,
and community hardening patterns (variable-driven roles, Molecule testing).
