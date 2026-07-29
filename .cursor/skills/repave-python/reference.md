# repave Python — reference (modern idioms and security)

Read when implementing **any** Python in this repo (engine, scripts, or new paths).

## Canonical patterns in this repo

| Concern | Module / pattern |
|---------|------------------|
| Subprocess + timeout | `subprocess_run.run_subprocess`, `gate_runners.run_command` |
| Gate PATH resolution | `gate_toolchain.resolve_tool`, `ensure_gate_path` |
| OIDC + sessions | `auth.py` — `secrets.token_urlsafe`, httpx timeouts, `require_role` |
| Acting user | `auth_context.set_acting_user` / `reset_acting_user` |
| YAML config | `yaml.safe_load(path.read_text(encoding="utf-8"))` |
| Outbound HTTP | `httpx` with explicit `timeout`; narrow exception handling |

## Modern typing (mypy strict)

```python
from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Final, Protocol

DEFAULT_TIMEOUT: Final = 15.0


class GateRunner(Protocol):
    def __call__(self, output_dir: Path) -> GateResult: ...
```

- Prefer **`Mapping[str, str]`** over `dict` in read-only APIs.
- Use **`TypeAlias`** or **`Protocol`** instead of untyped `Callable[..., Any]` when the shape matters.
- **`TypedDict`** for fixed JSON/session payload shapes when mypy should enforce keys.

## FastAPI / portal

- Declare dependencies and role checks at route level; mirror existing routers in `api.py` / related modules.
- Return generic **401/403** messages; put detail in server logs, not client bodies, when it could aid attackers.
- Validate and bound upload sizes and content types if adding file endpoints (multipart).

## Subprocess checklist

1. argv is **`list[str]`**, first element is resolved binary or `sys.executable`.
2. **`cwd`** is a resolved directory under staging or repo root.
3. **`timeout`** set (directly or via `run_subprocess`).
4. Capture stderr for gate failures; redact tokens before persisting logs or portal JSON.

## Bandit expectations

Bandit scans `engine/src` with project config. Common findings to fix rather than `# nosec`:

- Hardcoded passwords or tokens
- `shell=True`
- Unsafe YAML/XML loads
- Weak crypto (not typical here)

Documented skips in pyproject (`B404`, `B603`) cover intentional subprocess use — new subprocess call sites should use the shared helpers so reviewers see one pattern.

## Dependency hygiene

1. Add runtime deps only to `[project.dependencies]` with a lower bound (`>=`) consistent with existing entries.
2. `make lock` → commit `engine/uv.lock`.
3. Run **`make security`**; if pip-audit reports CVEs, bump the affected package and re-lock.
4. CI uses **`uv sync --frozen`** — lockfile must match pyproject.

## Tests for security-sensitive behavior

- Negative tests: invalid paths, missing auth, malformed YAML/JSON, timeout subprocess.
- Do not commit real tokens; use **`monkeypatch.setenv`** and fixtures under `engine/tests/`.
- For auth regressions, follow patterns in `tests/test_auth.py` and API tests.

## External guidance (align with, do not duplicate)

- [PEP 484 / typing docs](https://docs.python.org/3/library/typing.html) — unions, Protocol, Final
- [OWASP Python security](https://owasp.org/www-project-python-security/) — deserialization, injection, secrets
- [Bandit documentation](https://bandit.readthedocs.io/) — finding codes
- [Astral Ruff rules](https://docs.astral.sh/ruff/rules/) — enabled set is in `pyproject.toml` (`E`, `F`, `I`, `UP`, `B`, `SIM`, `RUF`)
