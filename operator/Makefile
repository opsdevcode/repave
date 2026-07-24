# Image URL to use for all building/pushing image targets
IMG ?= repave-operator:dev

# ENVTEST_K8S_VERSION refers to the Kubernetes version for envtest assets.
ENVTEST_K8S_VERSION = 1.31.0

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

.PHONY: test
test: manifests generate envtest
	KUBEBUILDER_ASSETS="$(shell $(ENVTEST) use $(ENVTEST_K8S_VERSION) --bin-dir $(LOCALBIN) -p path)" go test $$(go list ./... | grep -v /e2e) -coverprofile cover.out

.PHONY: lint
lint: golangci-lint
	$(GOLANGCI_LINT) run ./...

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
	$(call go-install-tool,$(CONTROLLER_GEN),sigs.k8s.io/controller-tools/cmd/controller-gen,v0.17.2)

.PHONY: envtest
envtest: $(ENVTEST)

$(ENVTEST): $(LOCALBIN)
	$(call go-install-tool,$(ENVTEST),sigs.k8s.io/controller-runtime/tools/setup-envtest,latest)

.PHONY: golangci-lint
golangci-lint: $(GOLANGCI_LINT)

$(GOLANGCI_LINT): $(LOCALBIN)
	$(call go-install-tool,$(GOLANGCI_LINT),github.com/golangci/golangci-lint/cmd/golangci-lint,v1.62.2)

.PHONY: e2e
e2e:
	@echo "kind e2e harness not implemented yet (v1.17 pre-GA); see docs/operator-local-dev.md"

# go-install-tool installs a Go tool if not present in $(GOBIN) or $(LOCALBIN).
define go-install-tool
@[ -f "$(1)" ] || { \
set -e; \
echo "Installing $(2)"; \
GOBIN=$(LOCALBIN) go install $(2)@$(3); \
}
endef
