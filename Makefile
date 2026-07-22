.PHONY: install test lint format typecheck security quality serve compose-up compose-down list generate

REPO_ROOT := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))

install:
	cd engine && python -m pip install -e '.[dev]'

test:
	cd engine && pytest

lint:
	cd engine && ruff check src tests

format:
	cd engine && ruff format src tests

typecheck:
	cd engine && mypy src

security:
	cd engine && bandit -r src -c pyproject.toml && pip-audit

quality: lint typecheck
	@cd engine && ruff format --check src tests

serve:
	cd engine && repave serve --repo-root $(REPO_ROOT) --host 127.0.0.1 --port 8080

list:
	cd engine && repave list --repo-root $(REPO_ROOT)

generate:
	cd engine && repave generate \
	  --repo-root $(REPO_ROOT) \
	  --blueprint blueprints/terraform-module-generic \
	  --input module_name=example \
	  --input description="Example module" \
	  --dry-run

compose-up:
	cd deploy/local && docker compose up --build

compose-down:
	cd deploy/local && docker compose down
