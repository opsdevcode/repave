# Ansible role standard (v0.1.0)

Baseline expectations for roles generated from the `ansible-role-generic`
blueprint. A fuller standard and ansible-lint policy pack ship in v1.16.

## Layout

- `meta/main.yml` — Galaxy metadata with pinned `min_ansible_version` and platforms
- `tasks/main.yml` — primary role tasks
- `defaults/main.yml` — default variable values
- `handlers/main.yml` — handlers (may be empty scaffold)
- `vars/` — internal variables (optional)
- `molecule/default/` — Molecule scenario for converge + verify
- `README.md` — rendered usage documentation with a `## Usage` section
- `repave.yaml` — provenance metadata validated by the `provenance-drift` gate

## Quality gates

Generated roles run `yamllint`, `ansible-lint`, `ansible-syntax-check`,
`molecule`, `docs-drift`, and `provenance-drift` before publish. Tooling gates
skip cleanly when the binary is not installed locally.
