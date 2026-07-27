# Ansible catalog

Community **role patterns** for `ansible-role-generic` (`ansible/catalog.json`).

| Path | Purpose |
| --- | --- |
| `catalog.json` | `role_patterns` registry and portal form presets |
| `roles/<pattern>/` | Jinja fragments materialized into generated roles |
| `requirements-gate-collections.yml` | Collections for local `make test` and CI gate toolchain |

Patterns are rendered at generate time (see `engine/src/repave_engine/ansible_pattern.py`).
