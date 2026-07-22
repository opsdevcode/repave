# repave operator (v0.2)

The reconciliation operator is planned for **v0.2**.

It will watch generated repositories and reconcile them against pinned blueprint
and standard versions, opening governed remediation/upgrade pull requests when:

- generated code or docs drift from the blueprint contract, or
- a pinned standard version bumps and the estate needs upgrading.

## Planned CRDs

- `GoldenPathRepo` — a generated artifact + pinned blueprint/standard version + desired state
- `Blueprint` — registry of golden paths and versions

## Framework

Operator SDK (Go core reconciler), with the door open for Ansible/Helm-based
operator flavors so more contributors can participate.

## v0.1 focus

v0.1 proves the generation loop locally:

form → deterministic render → gates → governed PR plan

The operator builds on the stable contracts frozen in `schemas/` and
`blueprints/`.
