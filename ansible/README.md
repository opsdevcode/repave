# Ansible catalog

Community **role**, **playbook**, and **collection sample** patterns for Ansible golden paths (`ansible/catalog.json`).

| Path | Purpose |
| --- | --- |
| `catalog.json` | `role_patterns`, `playbook_patterns`, and `collection_sample_patterns` registries |
| `roles/<pattern>/` | Jinja fragments materialized into generated roles |
| `playbooks/<pattern>/` | Jinja fragments materialized into generated playbook projects |
| `requirements-gate-collections.yml` | Collections for local `make test` and CI gate toolchain |

Patterns are rendered at generate time (see `engine/src/repave_engine/ansible_pattern.py`).

**Playbook patterns:** `repave-baseline`, `linux-patch-baseline`, `windows-update-baseline`, and
`pinned-roles-rollout` (requires at least one portal-pinned Galaxy role).
