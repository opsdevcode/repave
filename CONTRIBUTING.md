# Contributing to repave

Thanks for your interest in `repave`. This project is in early development
(v0.1), so the most valuable contributions right now are feedback on the core
contracts and the generation loop.

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

## Pull requests

- Keep changes small and focused.
- Include tests for engine logic changes.
- Explain intent and any trade-offs in the PR description.

## Reporting issues

Use GitHub issues. For anything security-sensitive, follow
[SECURITY.md](SECURITY.md) instead of filing a public issue.
