.PHONY: install lock test test-fast test-core test-portal test-slow test-v3 test-parallel integration-test lint format typecheck security quality js-lint backstage-lint backstage-test changelog serve platform-dev-setup compose-up compose-down list generate operator-test operator-lint operator-run operator-e2e blueprint-conformance-check blueprint-conformance-update sync-doc-versions sync-chart-versions sync-versions-lock chart-validate chart-smoke chart-smoke-decomposed chart-smoke-multi-replica chart-smoke-environment-vending chart-smoke-fleet-snapshot chart-smoke-backstage validate-github-repo-fleet postgres-dr-drill kind-co-install gate-doctor cli-install cli-test cli-test-fast cli-lint cli-format cli-typecheck cli-security cli-quality

REPO_ROOT := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
MODULES_ROOT ?= $(HOME)/repave-modules
GITHUB_ORG ?= opsdevcode
REPAVE_ENV = REPAVE_GITHUB_ORG=$(GITHUB_ORG) REPAVE_MODULES_ROOT=$(MODULES_ROOT)
ENGINE_PYTEST = PATH="$(REPO_ROOT)/.gate-tools/bin:$$PATH" uv run pytest
PORTAL_TEST_FILES = \
	tests/test_api.py \
	tests/test_api_read_models.py \
	tests/test_api_token_auth.py \
	tests/test_api_v2.py
PORTAL_TEST_GLOBS = tests/test_portal_*.py tests/test_platform_*.py
CORE_TEST_IGNORES = \
	--ignore=tests/test_api.py \
	--ignore=tests/test_api_read_models.py \
	--ignore=tests/test_api_token_auth.py \
	--ignore=tests/test_api_v2.py \
	--ignore-glob=tests/test_portal_*.py \
	--ignore-glob=tests/test_platform_*.py \
	--ignore=tests/test_blueprint_conformance.py \
	--ignore=tests/test_blueprint_conformance_helpers.py

install:
	cd engine && uv sync --extra dev

lock:
	cd engine && uv lock

changelog:
	cd engine && uv run semantic-release changelog

sync-doc-versions:
	python3 scripts/sync_doc_versions.py

sync-chart-versions:
	python3 scripts/sync_chart_versions.py

sync-versions-lock:
	python3 scripts/sync_versions_lock.py

policy-standards-watch:
	python3 scripts/sync_policy_standards.py --update


test:
	cd engine && $(ENGINE_PYTEST) --cov=repave_engine --cov-report=term-missing

# Daily dev loop: skip slow integration/conformance tests and coverage (run `make test` before push).
test-fast:
	cd engine && $(ENGINE_PYTEST) -m "not slow" --no-cov -q

test-core:
	cd engine && $(ENGINE_PYTEST) -m "not slow" $(CORE_TEST_IGNORES) \
	  $(if $(COV),-n auto --cov=repave_engine --cov-report=term-missing,--no-cov -q)

test-portal:
	cd engine && $(ENGINE_PYTEST) $(PORTAL_TEST_FILES) $(PORTAL_TEST_GLOBS) --no-cov -q

test-slow:
	cd engine && $(ENGINE_PYTEST) -m slow \
	  tests/test_blueprint_conformance.py tests/test_blueprint_conformance_helpers.py --no-cov -q

test-v3:
	cd engine && $(ENGINE_PYTEST) -m v3 --no-cov -q

integration-test:
	cd engine && uv run pytest ../integration/tests -q

# After deploy/local/install-gate-toolchain.sh (same pins CI and Compose assert).
gate-doctor:
	cd engine && PATH="$(REPO_ROOT)/.gate-tools/bin:$(REPO_ROOT)/.gate-tools/py-deps/bin:$$PATH" \
	  PYTHONPATH="$(REPO_ROOT)/.gate-tools/py-deps" \
	  uv run repave doctor --strict --repo-root $(REPO_ROOT)

# Full suite with parallel workers (requires pytest-xdist; gate tools on PATH).
test-parallel:
	cd engine && $(ENGINE_PYTEST) -n auto --cov=repave_engine --cov-report=term-missing

blueprint-conformance-check:
	cd engine && uv run python ../scripts/check_blueprint_conformance_manifests.py

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

# Bundled Yarn 4 (asdf has no yarn shim). CI uses corepack enable.
BACKSTAGE_YARN = node .yarn/releases/yarn-4.13.0.cjs

backstage-lint:
	cd backstage && $(BACKSTAGE_YARN) install --immutable && $(BACKSTAGE_YARN) tsc && $(BACKSTAGE_YARN) lint:all

backstage-test:
	cd backstage && $(BACKSTAGE_YARN) test --watch=false

# repave-cli (ADR 004). Installed with the engine's server extra so the import
# boundary tests can prove the client does not reach for FastAPI or a database.
cli-install:
	cd cli && uv venv && uv pip install -e ".[dev]" -e "../engine[server]"

cli-test:
	cd cli && uv run --no-project pytest --cov=repave_cli --cov-report=term-missing

cli-test-fast:
	cd cli && uv run --no-project pytest -m "not slow" --no-cov -q

cli-lint:
	cd cli && uv run --no-project ruff check src tests

cli-format:
	cd cli && uv run --no-project ruff format src tests

cli-typecheck:
	cd cli && uv run --no-project mypy src

cli-security:
	cd cli && uv run --no-project bandit -r src -c pyproject.toml

cli-quality: cli-lint cli-typecheck
	@cd cli && uv run --no-project ruff format --check src tests

platform-dev-setup:
	bash scripts/setup-platform-dev.sh

serve:
	mkdir -p $(MODULES_ROOT)
	cd engine && PATH="$(REPO_ROOT)/.gate-tools/bin:$$PATH" $(REPAVE_ENV) \
		REPAVE_SERVICE_CATALOG=1 REPAVE_ENV=local \
		uv run repave serve --repo-root $(REPO_ROOT) --host 127.0.0.1 --port 8089

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
	chmod +x deploy/k8s/hack/validate-chart.sh deploy/k8s/hack/validate-operator-chart.sh
	./deploy/k8s/hack/validate-chart.sh
	./deploy/k8s/hack/validate-operator-chart.sh

chart-smoke:
	chmod +x deploy/k8s/hack/chart-smoke.sh
	./deploy/k8s/hack/chart-smoke.sh

chart-smoke-decomposed:
	chmod +x deploy/k8s/hack/chart-smoke-decomposed.sh
	./deploy/k8s/hack/chart-smoke-decomposed.sh

chart-smoke-multi-replica:
	chmod +x deploy/k8s/hack/chart-smoke-multi-replica.sh
	./deploy/k8s/hack/chart-smoke-multi-replica.sh

chart-smoke-environment-vending:
	chmod +x deploy/k8s/hack/chart-smoke-environment-vending.sh
	./deploy/k8s/hack/chart-smoke-environment-vending.sh

chart-smoke-fleet-snapshot:
	chmod +x deploy/k8s/hack/chart-smoke-fleet-snapshot.sh
	./deploy/k8s/hack/chart-smoke-fleet-snapshot.sh

chart-smoke-backstage:
	chmod +x deploy/k8s/hack/chart-smoke-backstage.sh
	./deploy/k8s/hack/chart-smoke-backstage.sh

# Tier A ops smoke: simulate github-repo fleet register → fleet-manifests (no live GitHub).
# Docs: docs/operations/github-repo-fleet-validation.md
validate-github-repo-fleet:
	chmod +x scripts/validate-github-repo-fleet.sh
	./scripts/validate-github-repo-fleet.sh

postgres-dr-drill:
	chmod +x deploy/k8s/hack/postgres-dr-drill.sh
	./deploy/k8s/hack/postgres-dr-drill.sh

kind-co-install:
	chmod +x deploy/k8s/hack/kind-co-install.sh
	./deploy/k8s/hack/kind-co-install.sh
