# Image URL to use for all building/pushing image targets
IMG ?= repave-operator:dev

# ENVTEST_K8S_VERSION refers to the Kubernetes version for envtest assets.
ENVTEST_K8S_VERSION = 1.36.0

# Get the currently used golang install path (in GOPATH/bin, if GOBIN is not set).
GOBIN ?= $(shell go env GOPATH)/bin
ENVTEST ?= $(LOCALBIN)/setup-envtest
CONTROLLER_GEN ?= $(LOCALBIN)/controller-gen

# Setting SHELL to bash allows bash commands to be executed by recipes.
SHELL = /usr/bin/env bash -o pipefail
.SHELLFLAGS = -ec

.PHONY: all
all: generate manifests test

##@ Development

.PHONY: generate
generate: controller-gen
	$(CONTROLLER_GEN) object:headerFile="hack/boilerplate.go.txt" paths="./..."

.PHONY: manifests
manifests: controller-gen
	$(CONTROLLER_GEN) rbac:roleName=manager-role paths="./internal/..."
	$(CONTROLLER_GEN) crd paths="./api/..." output:crd:artifacts:config=config/crd/bases
	chmod +x hack/patch-crd-conversion.sh
	hack/patch-crd-conversion.sh

.PHONY: test
test: manifests generate envtest
	@assets="$$($(ENVTEST) use $(ENVTEST_K8S_VERSION) --bin-dir $(LOCALBIN) -p path)"; \
	if [ -z "$$assets" ] || [ ! -d "$$assets" ]; then \
	  echo "envtest assets missing (setup-envtest download failed for $(ENVTEST_K8S_VERSION))" >&2; \
	  exit 1; \
	fi; \
	KUBEBUILDER_ASSETS="$$assets" go test $$(go list ./... | grep -v /e2e) -coverprofile cover.out

.PHONY: lint
lint: golangci-lint
	$(GOLANGCI_LINT) run ./...

.PHONY: govulncheck
govulncheck:
	go run golang.org/x/vuln/cmd/govulncheck@v1.1.4 ./...

.PHONY: run
run: manifests generate
	go run ./cmd/main.go

##@ Build

.PHONY: build
build: generate
	go build -o bin/manager ./cmd/main.go

.PHONY: docker-build
docker-build:
	docker build -t ${IMG} .

GOLANGCI_LINT ?= $(LOCALBIN)/golangci-lint

##@ Dependencies

LOCALBIN ?= $(shell pwd)/bin
$(LOCALBIN):
	mkdir -p $(LOCALBIN)

.PHONY: controller-gen
controller-gen: $(CONTROLLER_GEN)

$(CONTROLLER_GEN): $(LOCALBIN)
	$(call go-install-tool,$(CONTROLLER_GEN),sigs.k8s.io/controller-tools/cmd/controller-gen,v0.21.0)

.PHONY: envtest
envtest: $(ENVTEST)

$(ENVTEST): $(LOCALBIN)
	$(call go-install-tool,$(ENVTEST),sigs.k8s.io/controller-runtime/tools/setup-envtest,v0.24.1)

.PHONY: golangci-lint
golangci-lint: $(GOLANGCI_LINT)

$(GOLANGCI_LINT): $(LOCALBIN)
	$(call go-install-tool,$(GOLANGCI_LINT),github.com/golangci/golangci-lint/cmd/golangci-lint,v1.62.2)

.PHONY: e2e
e2e:
	bash hack/e2e.sh

# go-install-tool installs a Go tool if not present in $(GOBIN) or $(LOCALBIN).
define go-install-tool
@[ -f "$(1)" ] || { \
set -e; \
echo "Installing $(2)"; \
GOBIN=$(LOCALBIN) go install $(2)@$(3); \
}
endef
