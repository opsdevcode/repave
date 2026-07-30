.PHONY: install lock test test-fast test-parallel lint format typecheck security quality js-lint changelog serve compose-up compose-down list generate operator-test operator-lint operator-run operator-e2e blueprint-conformance-update sync-doc-versions chart-validate chart-smoke chart-smoke-decomposed kind-co-install gate-doctor

REPO_ROOT := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
MODULES_ROOT ?= $(HOME)/repave-modules
GITHUB_ORG ?= opsdevcode
REPAVE_ENV = REPAVE_GITHUB_ORG=$(GITHUB_ORG) REPAVE_MODULES_ROOT=$(MODULES_ROOT)

install:
	cd engine && uv sync --extra dev

lock:
	cd engine && uv lock

changelog:
	cd engine && uv run semantic-release changelog

sync-doc-versions:
	python3 scripts/sync_doc_versions.py

policy-standards-watch:
	python3 scripts/sync_policy_standards.py --update


test:
	cd engine && PATH="$(REPO_ROOT)/.gate-tools/bin:$$PATH" uv run pytest --cov=repave_engine --cov-report=term-missing

# Daily dev loop: skip slow integration/conformance tests and coverage (run `make test` before push).
test-fast:
	cd engine && PATH="$(REPO_ROOT)/.gate-tools/bin:$$PATH" uv run pytest -m "not slow" --no-cov -q

# After deploy/local/install-gate-toolchain.sh (same pins CI and Compose assert).
gate-doctor:
	cd engine && PATH="$(REPO_ROOT)/.gate-tools/bin:$(REPO_ROOT)/.gate-tools/py-deps/bin:$$PATH" \
	  PYTHONPATH="$(REPO_ROOT)/.gate-tools/py-deps" \
	  uv run repave doctor --strict --repo-root $(REPO_ROOT)

# Full suite with parallel workers (requires pytest-xdist; gate tools on PATH).
test-parallel:
	cd engine && PATH="$(REPO_ROOT)/.gate-tools/bin:$$PATH" uv run pytest -n auto --cov=repave_engine --cov-report=term-missing

blueprint-conformance-update:
	cd engine && uv run python -c "from pathlib import Path; from repave_engine.blueprint_conformance import update_all_manifests; root=Path('..').resolve(); staging=root/'.conformance-staging'; staging.mkdir(exist_ok=True); mods=root/'.conformance-modules'; mods.mkdir(exist_ok=True); names=update_all_manifests(root, modules_root=mods, staging_root=staging); print('Updated manifests:', ', '.join(names) or '(none with snapshot: true)')"

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

js-lint:
	npm ci
	npm run lint:js

serve:
	mkdir -p $(MODULES_ROOT)
	cd engine && PATH="$(REPO_ROOT)/.gate-tools/bin:$$PATH" $(REPAVE_ENV) REPAVE_ENV=local uv run repave serve --repo-root $(REPO_ROOT) --host 127.0.0.1 --port 8089

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

operator-lint:
	cd operator && $(MAKE) lint

operator-run:
	cd operator && $(MAKE) run

operator-e2e:
	cd operator && $(MAKE) e2e

chart-validate:
	chmod +x deploy/k8s/hack/validate-chart.sh
	./deploy/k8s/hack/validate-chart.sh

chart-smoke:
	chmod +x deploy/k8s/hack/chart-smoke.sh
	./deploy/k8s/hack/chart-smoke.sh

chart-smoke-decomposed:
	chmod +x deploy/k8s/hack/chart-smoke-decomposed.sh
	./deploy/k8s/hack/chart-smoke-decomposed.sh

kind-co-install:
	chmod +x deploy/k8s/hack/kind-co-install.sh
	./deploy/k8s/hack/kind-co-install.sh
