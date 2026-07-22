# repave-engine

Core generation engine for [repave](../README.md).

## Install (development)

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e '.[dev]'
```

## CLI

```bash
repave generate \
  --blueprint ../blueprints/terraform-module-generic \
  --input module_name=example \
  --input description="Example module" \
  --dry-run
```

## Quality and security (local)

```bash
make quality   # ruff lint/format check + mypy
make security  # bandit + pip-audit
make test
```

## API (local portal backend)

```bash
repave serve --repo-root .. --host 0.0.0.0 --port 8080
```

Open http://localhost:8080 for the bundled web form.
