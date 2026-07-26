# Repave ansible-lint policy pack

Production-profile ansible-lint configuration for generated Ansible roles. Enforces
[role-standard.md](../standards/ansible/role-standard.md) and
[security-appendix.md](../standards/ansible/security-appendix.md).

Pack version is pinned in `blueprints/ansible-role-generic/blueprint.yaml` under
`spec.ansible_lint.pack_version`.

## Layout

```text
policy/ansible-lint/pack/    # Copied to generated role root at render time
examples/ansible-lint/tests/fixtures/
```

## Profile

- **production** — FQCN, sanity, single-entry-point, meta-no-dependencies, use-loop
- **enable_list** — `no-log-password`, `no-same-owner`, `yaml`
- **strict: true**

## Running locally

```bash
pip install ansible-lint yamllint
cd examples/ansible-lint/tests/fixtures/role-pass
ansible-lint
yamllint .
```

From repo root:

```bash
cd engine && python3 -m pytest tests/test_ansible_lint_policies.py -q
```

## Adding rules

1. Update `policy/ansible-lint/pack/.ansible-lint` or `policy/ansible-lint/pack/.yamllint`
2. Add pass/fail fixtures under `tests/fixtures/`
3. Extend `engine/tests/test_ansible_lint_policies.py`
4. Bump `pack_version` in the ansible-role blueprint
