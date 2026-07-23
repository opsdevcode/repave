# repave operator (planned)

The reconciliation operator is the next major milestone after **v1.8**.

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

## Current baseline (v1.8)

v1.8 proves the generation loop locally and publishes module repositories to
GitHub when configured:

form → deterministic render → gates → local module repo → GitHub push

Generated Terraform modules use one `.tf` file per scoped provider resource.
The operator builds on the stable contracts frozen in `schemas/` and
`blueprints/`.
