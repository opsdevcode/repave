.PHONY: install test lint format typecheck security quality serve compose-up compose-down list generate

REPO_ROOT := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
MODULES_ROOT ?= $(HOME)/repave-modules
GITHUB_ORG ?= opsdevcode
REPAVE_ENV = REPAVE_GITHUB_ORG=$(GITHUB_ORG) REPAVE_MODULES_ROOT=$(MODULES_ROOT)

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
	mkdir -p $(MODULES_ROOT)
	$(REPAVE_ENV) cd engine && repave serve --repo-root $(REPO_ROOT) --host 127.0.0.1 --port 8088

list:
	cd engine && repave list --repo-root $(REPO_ROOT)

generate:
	mkdir -p $(MODULES_ROOT)
	$(REPAVE_ENV) cd engine && repave generate \
	  --repo-root $(REPO_ROOT) \
	  --blueprint blueprints/terraform-module-generic \
	  --input module_name=example \
	  --input description="Example module" \
	  --input cloud_provider=aws \
	  --input provider_services=s3,vpc \
	  --dry-run

compose-up:
	cd deploy/local && docker compose up --build

compose-down:
	cd deploy/local && docker compose down
