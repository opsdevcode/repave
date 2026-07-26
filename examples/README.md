# examples/

Sample **fixtures and pack tests** for repave development and CI. This directory
is not copied into production service images.

Runtime packs and standards live at the repository root:

| Purpose | Service path |
| --- | --- |
| Terraform / Ansible standards corpus | `standards/` |
| Checkov custom policies | `policy/checkov/policies/` |
| Ansible production-profile lint pack | `policy/ansible-lint/pack/` |

Blueprints pin those paths in `blueprint.yaml`; generated modules receive copies
under their own `policy/` tree as today.

## Layout

```text
examples/
  checkov/tests/       # pass/fail Terraform fixtures for policy pack tests
  ansible-lint/tests/    # role fixtures for ansible-lint pack tests
```

See `policy/checkov/policies/` and `examples/checkov/README.md` for policy
authoring; see `standards/` for the governed module/role standard text.
