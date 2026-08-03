# Engine capabilities

Reference for what the generation engine (`engine/`) supports today. Product
overview: [README](../README.md).

## Golden paths

Terraform modules, environment stacks, Ansible roles, collections, playbook
projects, policy packs, observability bundles, Helm charts, and app-service
scaffolds under [`blueprints/`](../blueprints/). Rendering uses Copier; contracts
live in [`schemas/`](../schemas/) with versioning policy in
[`docs/blueprint-versioning.md`](blueprint-versioning.md).

## Portal and API

- Server-rendered forms, gate results dashboard, publish and update flows at
  `:8088` (`make serve` or [Docker Compose](quickstart.md)).
- HTTP generate API and Backstage lineage: [backstage.md](backstage.md).
- UX spec: [portal-design.md](portal-design.md).

## CLI

`repave generate`, `repave list`, `repave import` (adopt an existing repo into a golden path
layout — see [import.md](import.md)), `repave add` (layer a second blueprint onto a governed
repo — see [add.md](add.md)), `repave verify`, `repave update` (plan/apply blueprint
upgrades from `repave.yaml`), gate execution, provenance in `repave.yaml`.

## Gates (blueprint-configured)

**Terraform:** `fmt`, `validate`, `tflint`, Checkov (packs under
[`policy/checkov/`](../policy/checkov/)), secrets scanning.

**Ansible:** production-profile **ansible-lint** pack and standards under
[`standards/ansible/`](../standards/ansible/). **`ansible-role-generic`** materializes
community **role patterns** from [`ansible/catalog.json`](../ansible/catalog.json)
(`linux-service`, `windows-service`, optional `repave-baseline`). **`ansible-playbook-project`**
materializes **playbook patterns** (`linux-patch-baseline`, `windows-update-baseline`, optional
`repave-baseline`); generated roles and playbooks include `requirements.yml` when a pattern needs
collections. CI installs gate collections from
[`ansible/requirements-gate-collections.yml`](../ansible/requirements-gate-collections.yml).

**Policy:** OPA and Azure Policy gates where blueprints declare them — see
[`policy/`](../policy/) and [`standards/policy/`](../standards/policy/).

## CI on `main`

- Engine: pytest, Ruff, mypy, Bandit, pip-audit.
- Operator: Go tests + controller-runtime **envtest** on every PR.
