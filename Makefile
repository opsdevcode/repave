.PHONY: install lock test lint format typecheck security quality serve compose-up compose-down list generate operator-test operator-run operator-e2e

REPO_ROOT := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
MODULES_ROOT ?= $(HOME)/repave-modules
GITHUB_ORG ?= opsdevcode
REPAVE_ENV = REPAVE_GITHUB_ORG=$(GITHUB_ORG) REPAVE_MODULES_ROOT=$(MODULES_ROOT)

install:
	cd engine && uv sync --extra dev

lock:
	cd engine && uv lock

test:
	cd engine && uv run pytest --cov=repave_engine --cov-report=term-missing --cov-fail-under=75

lint:
	cd engine && uv run ruff check src tests

format:
	cd engine && uv run ruff format src tests

typecheck:
	cd engine && uv run mypy src

security:
	cd engine && uv run bandit -r src -c pyproject.toml && uv run pip-audit

quality: lint typecheck
	@cd engine && uv run ruff format --check src tests

serve:
	mkdir -p $(MODULES_ROOT)
	$(REPAVE_ENV) cd engine && uv run repave serve --repo-root $(REPO_ROOT) --host 127.0.0.1 --port 8088

list:
	cd engine && uv run repave list --repo-root $(REPO_ROOT)

generate:
	mkdir -p $(MODULES_ROOT)
	$(REPAVE_ENV) cd engine && uv run repave generate \
	  --repo-root $(REPO_ROOT) \
	  --blueprint blueprints/terraform-module-generic \
	  --input module_name=example \
	  --input description="Example module" \
	  --input cloud_provider=aws \
	  --input provider_services=ec2,s3 \
	  --dry-run

compose-up:
	cd deploy/local && docker compose up --build

compose-down:
	cd deploy/local && docker compose down

operator-test:
	cd operator && $(MAKE) test

operator-run:
	cd operator && $(MAKE) run

operator-e2e:
	cd operator && $(MAKE) e2e
