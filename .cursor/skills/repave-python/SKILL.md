---
name: repave-python
description: >-
  Python development anywhere in opsdevcode/repave: any .py path, engine package,
  pytest, Ruff, mypy, Bandit, pip-audit, modern 3.12+ idioms, and security patterns.
  Use when writing or editing Python in this repo, pyproject.toml, or fixing Python
  quality and security CI.
---

# repave Python development

**Scope:** all Python in this monorepo (`engine/`, `scripts/`, and any other `**/*.py`).
Follow **`.cursor/rules/python-standards.mdc`** and **`.cursor/rules/python-security.mdc`**
for every Python change.

## Source of truth

| Topic | Location |
|-------|----------|
| Ruff, mypy, pytest, coverage, bandit | `engine/pyproject.toml` |
| Make targets | root `Makefile` |
| CI job | `.github/workflows/python-quality-security.yml` |
| Cursor rules | `.cursor/rules/python-standards.mdc`, `.cursor/rules/python-security.mdc` |
| Deep reference | [reference.md](reference.md) |
| Contributing | `CONTRIBUTING.md` |

## Environment

```bash
make install          # uv sync --extra dev in engine/
cd engine && uv run pytest   # equivalent to make test (from root, prefer make test)
```

Requires [uv](https://docs.astral.sh/uv/). Gate-toolchain tests need `.gate-tools/bin` on PATH (root `Makefile` sets this for `make test`).

## Quality workflow

Always run before commit (see `.cursor/rules/pre-commit.mdc`):

```bash
make format && make quality && make security && make test
```

| Target | What it runs |
|--------|----------------|
| `make lint` | `ruff check src tests` |
| `make format` | `ruff format src tests` |
| `make typecheck` | `mypy src` |
| `make quality` | lint + format check + mypy |
| `make security` | bandit on `src` + pip-audit |
| `make test-fast` | pytest `-m "not slow"`, no cov |
| `make test` | full suite, coverage ≥ 75% |

Fix Ruff **E501** by wrapping to **100 columns**, not by disabling rules.

### Python outside `engine/` (`scripts/`, etc.)

CI gates **`engine/src`** and **`engine/tests`**. Still apply the same Ruff settings
from `engine/pyproject.toml`:

```bash
cd engine
uv run ruff check ../scripts/path/to/file.py
uv run ruff format ../scripts/path/to/file.py
```

For subprocess, HTTP, or parsing in non-engine Python, run Bandit on the path:

```bash
cd engine && uv run bandit -r ../scripts -c pyproject.toml
```

Add or extend **`engine/tests/`** when behavior belongs to the engine; for standalone
scripts, include tests when the script encodes non-trivial logic (see existing
`tests/test_sync_doc_versions.py`).

## Coding conventions (engine)

Match neighboring modules in `engine/src/repave_engine/`:

1. **`from __future__ import annotations`** at top of new files.
2. **Typed public API** — mypy `disallow_untyped_defs` applies to `repave_engine`.
3. **Pathlib** for filesystem paths; **dataclasses** for structured results (e.g. `RenderResult`, `GateResult`).
4. **Deterministic behavior** — no random or time-dependent template output without explicit inputs.
5. **Gates are mandatory** — do not add paths that skip configured blueprint gates.
6. **Stable contracts** — schema changes under `schemas/` need explicit discussion and semver policy.

Import style: stdlib → third party → `repave_engine.*` (Ruff isort).

## Modern Python (summary)

Follow **`.cursor/rules/python-standards.mdc`**: post-3.9 typing (`|`, `collections.abc`), frozen dataclasses for config, `logging` over print, specific exceptions with chaining, judicious `match/case`.

## Security (summary)

Follow **`.cursor/rules/python-security.mdc`**:

- Subprocess via **`run_subprocess`** / **`run_command`**, never `shell=True`.
- **`yaml.safe_load`** only; validate structured input with **jsonschema** where schemas exist.
- **httpx** always with **timeouts**; no secrets in logs; **FastAPI** routes must use existing auth/role helpers.
- **`make lock`** + **`make security`** with dependency changes.

Implementation checklists and repo examples: **[reference.md](reference.md)**.

## Tests

- Place tests in `engine/tests/test_<area>.py`.
- Use **`pytest.raises`** for expected errors; **`tmp_path`** / fixtures for filesystem work.
- Mark slow integration (Copier render, real gate binaries, conformance) with **`@pytest.mark.slow`**.
- Blueprint conformance: `conformance.yaml` per blueprint; refresh manifests with `make blueprint-conformance-update` when snapshot output changes.

Example shape (from existing tests):

```python
def test_parse_inputs_invalid() -> None:
    with pytest.raises(ValueError, match="Invalid --input value"):
        _parse_inputs(["not-valid"])
```

## Repo scripts and other Python

Standalone utilities under **`scripts/`** (and any future repo-root Python) use the
same standards as the engine: **`from __future__ import annotations`**, pathlib,
100-column Ruff, typed public functions, and **`.cursor/rules/python-security.mdc`**.

Run with **`python3`** or **`cd engine && uv run python ../scripts/...`** from repo root.
Doc-version sync runs in Release CI after semver bumps (`make sync-doc-versions`).

## Common CI failures

| Failure | Fix |
|---------|-----|
| `ruff format --check` | `make format` |
| mypy on new function | Add full annotations; avoid untyped `def` in `repave_engine` |
| Coverage below 75% | Add tests for new branches |
| Lockfile drift | `make lock` after dependency edits |
| Bandit finding | Fix code or justify in PR; avoid new `# nosec` without review |
| pip-audit CVE | Bump dependency, re-lock, re-run `make security` |

## Related

- Monorepo overview: `.cursor/skills/repave/SKILL.md` (or `~/.cursor/skills/repave/SKILL.md`)
- Release / semver: `.cursor/skills/repave-release/SKILL.md`
