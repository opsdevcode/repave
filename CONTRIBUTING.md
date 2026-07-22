# Contributing to repave

Thanks for your interest in `repave`. **v1.0** established the core generation
loop; the most valuable contributions now are feedback on contracts, golden
paths, and the operator design for v1.1.

## Ground rules

- **Keep the core cloud-agnostic.** Nothing cloud-specific belongs in `engine/`.
  Clouds live only in `blueprints/`.
- **The gates are not optional.** Do not add a code path that lets generated
  output skip its configured gates.
- **Contracts are stable.** Changes to `schemas/blueprint.schema.json` or
  `schemas/inputs.schema.json` are breaking and require a version bump and
  discussion first.
- **Deterministic generation.** Rendering must be reproducible for the same
  inputs; avoid nondeterministic template logic.

## Development

```bash
cd engine
python -m venv .venv && . .venv/bin/activate
pip install -e '.[dev]'
pytest
```

From repo root, quality and security checks:

```bash
make quality    # ruff lint + format check + mypy
make security   # bandit + pip-audit
make test
```

### Python quality and security tooling

CI runs these OSS tools on every push and pull request:

| Tool | Purpose |
| --- | --- |
| [Ruff](https://docs.astral.sh/ruff/) | Linting and formatting |
| [mypy](https://mypy-lang.org/) | Static type checking |
| [Bandit](https://bandit.readthedocs.io/) | Python SAST security scan |
| [pip-audit](https://pypi.org/project/pip-audit/) | Dependency vulnerability scan (OSV) |

Configuration lives in `engine/pyproject.toml`.

## Commit messages (Conventional Commits)

This repository uses [Conventional Commits](https://www.conventionalcommits.org/)
for automated releases via
[python-semantic-release](https://python-semantic-release.readthedocs.io/).

Format:

```text
<type>[optional scope]: <description>

[optional body]

[optional footer(s)]
```

Common types:

- `feat:` — new feature (**minor** version bump)
- `fix:` — bug fix (**patch** version bump)
- `feat!:` or `fix!:` / `BREAKING CHANGE:` footer — **major** version bump
- `docs:`, `chore:`, `ci:`, `refactor:`, `test:`, `build:` — no release bump unless they include breaking changes

Examples:

```text
feat(engine): add ansible-role blueprint scaffold
fix(gates): skip tflint when binary is unavailable
feat!: rename blueprint input schema fields
```

Pull request titles are also validated against Conventional Commits. Use the
same pattern for PR titles (for example `feat: add local docker quickstart`).

## Pull requests

- Keep changes small and focused.
- Use a Conventional Commit-style PR title.
- Include tests for engine logic changes.
- Explain intent and any trade-offs in the PR description.

## Reporting issues

Use GitHub issues. For anything security-sensitive, follow
[SECURITY.md](SECURITY.md) instead of filing a public issue.
