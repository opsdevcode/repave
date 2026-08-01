# Releases

Versioning and GitHub releases are automated from
[Conventional Commits](https://www.conventionalcommits.org/) on `main` using
[python-semantic-release](https://python-semantic-release.readthedocs.io/).

## Flow

1. Merge a PR to `main` with a conventional title (`feat:`, `fix:`, etc.).
2. The **Release** workflow runs engine + operator tests, then bumps semver,
   updates `engine/CHANGELOG.md`, and opens an admin-merged
   `chore/release/<version>` PR (protected `main` cannot take direct bot pushes).
3. After merge, the workflow tags the release commit and publishes a **GitHub
   Release** with `repave-engine` wheel/sdist artifacts via `gh release create`.

## Maintainer notes

- Authenticates with **`REPAVE_RELEASE_TOKEN`** (Administrator PAT).
- Docs-only merges skip the release job; `docs` / `chore` / `ci` commits do not
  bump version unless they include breaking changes.
- Release CI unsets `GITHUB_OUTPUT` for python-semantic-release CLI calls (see
  `psr()` in `.github/workflows/release.yml`).

Feature PRs must **not** hand-edit `engine/pyproject.toml` version. Preview
changelog on `main`: `make changelog`.

See [CONTRIBUTING.md](../CONTRIBUTING.md) for commit format and setup.

## Roadmap milestones and engine semver

Major **roadmap** themes align with **engine major** semver on `main`:

| Roadmap milestone | Engine tag | Trigger |
| --- | --- | --- |
| **v2.0.0 Platform GA** (contract freeze) | **`v2.0.0`** | `feat!:` or `BREAKING CHANGE:` when contract freeze ships |
| v2.x follow-ons (e.g. conversational AI) | `v2.1.0`, `v2.2.0`, … | `feat:` on the v2 line |
| **v3.0.0** (autonomous estate) | **`v3.0.0`** | Breaking removals (`/api/v1`, CRD promotions, etc.) |

Until v2.0.0 merges, releases stay on the v1 line (`v1.130.0`, …) even while v2
**themes** land incrementally. After v2.0.0, `feat:` bumps the **minor** (`v2.1.0`),
not the major — the roadmap “v2.0.0” label and the engine tag match at the
contract-freeze cut.

Release automation updates **Current release** in [`docs/roadmap.md`](roadmap.md),
`README.md`, and related doc pointers via `scripts/sync_doc_versions.py` — do not
hand-edit those lines in feature PRs.

Contract-freeze breaking surface (already on `main`; summarized at v2.0.0 tag):

- `/api/v1` deprecated — [`docs/api-v1-migration.md`](api-v1-migration.md)
- `repave.config.yaml` `apiVersion: repave.dev/v1` — [`docs/repave-config-v1.md`](repave-config-v1.md)
- Publish requires valid `repave.yaml` provenance
- Blueprint JSON Schema v2 line — [`docs/blueprint-versioning.md`](blueprint-versioning.md)
