# Ansible catalog

Community **role** and **playbook** patterns for Ansible golden paths (`ansible/catalog.json`).

| Path | Purpose |
| --- | --- |
| `catalog.json` | `role_patterns` and `playbook_patterns` registries and portal form presets |
| `roles/<pattern>/` | Jinja fragments materialized into generated roles |
| `playbooks/<pattern>/` | Jinja fragments materialized into generated playbook projects |
| `requirements-gate-collections.yml` | Collections for local `make test` and CI gate toolchain |

Patterns are rendered at generate time (see `engine/src/repave_engine/ansible_pattern.py`).
