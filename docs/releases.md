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
