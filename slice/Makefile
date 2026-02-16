# Copyright 2025 The Kubernetes Authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# Get the currently used golang install path (in GOPATH/bin, unless GOBIN is set)
ifeq (,$(shell go env GOBIN))
GOBIN=$(shell go env GOPATH)/bin
else
GOBIN=$(shell go env GOBIN)
endif

GO_VERSION := $(shell awk '/^go /{print $$2}' go.mod|head -n1)

BASE_IMAGE ?= gcr.io/distroless/static:nonroot
BUILDER_IMAGE ?= golang:$(GO_VERSION)
CGO_ENABLED ?= 0

PLATFORMS ?= linux/amd64
HOST_IMAGE_PLATFORM ?= linux/$(shell go env GOARCH)

PROJECT_DIR := $(shell dirname $(abspath $(lastword $(MAKEFILE_LIST))))
BIN_DIR ?= $(PROJECT_DIR)/bin
ARTIFACTS ?= $(BIN_DIR)
TOOLS_DIR := $(PROJECT_DIR)/hack/tools

DOCKER_BUILDX_CMD ?= docker buildx
IMAGE_BUILD_CMD ?= $(DOCKER_BUILDX_CMD) build

# Setting SHELL to bash allows bash commands to be executed by recipes.
# Options are set to exit when a recipe line exits non-zero or a piped command fails.
SHELL = /usr/bin/env bash -o pipefail
.SHELLFLAGS = -ec

GIT_TAG ?= $(shell git describe --tags --dirty --always)

RELEASE_VERSION=v0.1.0
RELEASE_BRANCH=main

STAGING_REGISTRY := us-central1-docker.pkg.dev/k8s-staging-images
K8S_REGISTRY := registry.k8s.io
STAGING_IMAGE_REGISTRY := $(STAGING_REGISTRY)/slice
IMAGE_REGISTRY ?= $(STAGING_IMAGE_REGISTRY)
IMAGE_REPO := $(IMAGE_REGISTRY)/slice
IMAGE_TAG := $(IMAGE_REPO):$(GIT_TAG)

KIND_CLUSTER_NAME ?= kind
CREATE_KIND_CLUSTER ?= true

# Folder where the e2e tests are located.
E2E_K8S_VERSIONS ?= 1.33.1
E2E_K8S_VERSION ?= 1.33
E2E_K8S_FULL_VERSION ?= $(filter $(E2E_K8S_VERSION).%,$(E2E_K8S_VERSIONS))
# Default to E2E_K8S_VERSION.0 if no match is found
E2E_K8S_FULL_VERSION := $(or $(E2E_K8S_FULL_VERSION),$(E2E_K8S_VERSION).0)
E2E_KIND_VERSION ?= kindest/node:v$(E2E_K8S_FULL_VERSION)
E2E_RUN_ONLY_ENV ?= false

.PHONY: all
all: build

##@ General

# The help target prints out all targets with their descriptions organized
# beneath their categories. The categories are represented by '##@' and the
# target descriptions by '##'. The awk command is responsible for reading the
# entire set of makefiles included in this invocation, looking for lines of the
# file as xyz: ## something, and then pretty-format the target and help. Then,
# if there's a line with ##@ something, that gets pretty-printed as a category.
# More info on the usage of ANSI control characters for terminal formatting:
# https://en.wikipedia.org/wiki/ANSI_escape_code#SGR_parameters
# More info on the awk command:
# http://linuxcommand.org/lc3_adv_awk.php

.PHONY: help
help: ## Display this help.
	@awk 'BEGIN {FS = ":.*##"; printf "\nUsage:\n  make \033[36m<target>\033[0m\n"} /^[a-zA-Z_0-9-]+:.*?##/ { printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2 } /^##@/ { printf "\n\033[1m%s\033[0m\n", substr($$0, 5) } ' $(MAKEFILE_LIST)

##@ Development

.PHONY: manifests
manifests: controller-gen ## Generate WebhookConfiguration, ClusterRole and CustomResourceDefinition objects.
	$(CONTROLLER_GEN) rbac:roleName=manager-role crd webhook paths="./..." output:crd:artifacts:config=config/crd/bases

.PHONY: generate
generate: controller-gen ## Generate code containing DeepCopy, DeepCopyInto, and DeepCopyObject method implementations.
	$(CONTROLLER_GEN) object:headerFile="hack/boilerplate.go.txt" paths="./..."

.PHONY: fmt
fmt: ## Run go fmt against code.
	$(GO_CMD) fmt ./...

.PHONY: vet
vet: ## Run go vet against code.
	$(GO_CMD) vet ./...

.PHONY: test
test: manifests generate fmt vet setup-envtest ## Run tests.
	KUBEBUILDER_ASSETS="$(shell $(ENVTEST) use $(ENVTEST_K8S_VERSION) --bin-dir $(BIN_DIR) -p path)" $(GO_CMD) test $$(go list ./... | grep -v /e2e) -coverprofile cover.out

# TODO(user): To use a different vendor for e2e tests, modify the setup under 'tests/e2e'.
# The default setup assumes Kind is pre-installed and builds/loads the Manager Docker image locally.
# CertManager is installed by default; skip with:
# - CERT_MANAGER_INSTALL_SKIP=true
KIND_CLUSTER ?= slice-controller-test-e2e

.PHONY: test-e2e
test-e2e: kustomize yq dep-crds kind ginkgo run-test-e2e-$(E2E_KIND_VERSION:kindest/node:v%=%)

run-test-e2e-%: K8S_VERSION = $(@:run-test-e2e-%=%)
run-test-e2e-%:
	@echo Running e2e for k8s ${K8S_VERSION}
	E2E_KIND_VERSION="kindest/node:v$(K8S_VERSION)" KIND_CLUSTER_NAME=$(KIND_CLUSTER_NAME) CREATE_KIND_CLUSTER=$(CREATE_KIND_CLUSTER) \
		EXTERNAL_CRDS_DIR=$(EXTERNAL_CRDS_DIR) ARTIFACTS="$(ARTIFACTS)/$@" IMAGE_TAG=$(IMAGE_TAG) GINKGO_ARGS="$(GINKGO_ARGS)" \
		KUEUE_IMAGE=$(KUEUE_IMAGE) JOBSET_IMAGE=$(JOBSET_IMAGE) \
		TEST_LOG_LEVEL=$(TEST_LOG_LEVEL) E2E_RUN_ONLY_ENV=$(E2E_RUN_ONLY_ENV) \
		./hack/e2e-test.sh

.PHONY: lint
lint: golangci-lint ## Run golangci-lint linter
	$(GOLANGCI_LINT) run

.PHONY: lint-fix
lint-fix: golangci-lint ## Run golangci-lint linter and perform fixes
	$(GOLANGCI_LINT) run --fix

.PHONY: lint-config
lint-config: golangci-lint ## Verify golangci-lint linter configuration
	$(GOLANGCI_LINT) config verify

##@ Build

.PHONY: build
build: ## Build manager binary.
	$(GO_BUILD_ENV) $(GO_CMD) build -ldflags="$(LD_FLAGS)" -o bin/manager cmd/main.go

.PHONY: run
run: manifests generate fmt vet ## Run a controller from your host.
	$(GO_CMD) run ./cmd/main.go

.PHONY: image-build
image-build:
	$(IMAGE_BUILD_CMD) \
		-t $(IMAGE_TAG) \
		-t $(IMAGE_REPO):$(RELEASE_BRANCH) \
		--platform=$(PLATFORMS) \
		--build-arg BASE_IMAGE=$(BASE_IMAGE) \
		--build-arg BUILDER_IMAGE=$(BUILDER_IMAGE) \
		--build-arg CGO_ENABLED=$(CGO_ENABLED) \
		$(PUSH) \
		$(IMAGE_BUILD_EXTRA_OPTS) \
		./

# Build an image just for the host architecture that can be used for Kind E2E tests.
.PHONY: kind-image-build
kind-image-build: PLATFORMS=$(HOST_IMAGE_PLATFORM)
kind-image-build: PUSH=--load
kind-image-build: kind image-build

.PHONY: build-installer
build-installer: manifests generate kustomize ## Generate a consolidated YAML with CRDs and deployment.
	mkdir -p dist
	cd config/manager && $(KUSTOMIZE) edit set image controller=${IMG}
	$(KUSTOMIZE) build config/default > dist/install.yaml

##@ Deployment

ifndef ignore-not-found
  ignore-not-found = false
endif

.PHONY: install
install: manifests kustomize ## Install CRDs into the K8s cluster specified in ~/.kube/config.
	$(KUSTOMIZE) build config/crd | $(KUBECTL) apply -f -

.PHONY: uninstall
uninstall: manifests kustomize ## Uninstall CRDs from the K8s cluster specified in ~/.kube/config. Call with ignore-not-found=true to ignore resource not found errors during deletion.
	$(KUSTOMIZE) build config/crd | $(KUBECTL) delete --ignore-not-found=$(ignore-not-found) -f -

.PHONY: deploy
deploy: manifests kustomize ## Deploy controller to the K8s cluster specified in ~/.kube/config.
	cd config/manager && $(KUSTOMIZE) edit set image controller=${IMG}
	$(KUSTOMIZE) build config/default | $(KUBECTL) apply -f -

.PHONY: undeploy
undeploy: kustomize ## Undeploy controller from the K8s cluster specified in ~/.kube/config. Call with ignore-not-found=true to ignore resource not found errors during deletion.
	$(KUSTOMIZE) build config/default | $(KUBECTL) delete --ignore-not-found=$(ignore-not-found) -f -

##@ Dependencies

## Tool Binaries
KUBECTL ?= kubectl
KIND ?= $(BIN_DIR)/kind
KUSTOMIZE ?= $(BIN_DIR)/kustomize
GINKGO = $(BIN_DIR)/ginkgo
CONTROLLER_GEN ?= $(BIN_DIR)/controller-gen
ENVTEST ?= $(BIN_DIR)/setup-envtest
GOLANGCI_LINT ?= $(BIN_DIR)/golangci-lint
YQ ?= $(BIN_DIR)/yq

GO_CMD ?= go

## Tool Versions
KIND_VERSION ?= $(shell cd $(TOOLS_DIR); $(GO_CMD) list -m -f '{{.Version}}' sigs.k8s.io/kind)
KUSTOMIZE_VERSION ?= $(shell cd $(TOOLS_DIR); $(GO_CMD) list -m -f '{{.Version}}' sigs.k8s.io/kustomize/kustomize/v5)
GINKGO_VERSION ?= $(shell cd $(TOOLS_DIR); $(GO_CMD) list -m -f '{{.Version}}' github.com/onsi/ginkgo/v2)
CONTROLLER_GEN_VERSION ?= $(shell cd $(TOOLS_DIR); $(GO_CMD) list -m -f '{{.Version}}' sigs.k8s.io/controller-tools)
#ENVTEST_VERSION is the version of controller-runtime release branch to fetch the envtest setup script (i.e. release-0.20)
ENVTEST_VERSION ?= $(shell $(GO_CMD) list -m -f "{{ .Version }}" sigs.k8s.io/controller-runtime | awk -F'[v.]' '{printf "release-%d.%d", $$2, $$3}')
#ENVTEST_K8S_VERSION is the version of Kubernetes to use for setting up ENVTEST binaries (i.e. 1.31)
ENVTEST_K8S_VERSION ?= $(shell $(GO_CMD) list -m -f "{{ .Version }}" k8s.io/api | awk -F'[v.]' '{printf "1.%d", $$3}')
GOLANGCI_LINT_VERSION ?= $(shell cd $(TOOLS_DIR); $(GO_CMD) list -m -f '{{.Version}}' github.com/golangci/golangci-lint/v2)
YQ_VERSION ?= $(shell cd $(TOOLS_DIR); $(GO_CMD) list -m -f '{{.Version}}' github.com/mikefarah/yq/v4)

KUEUE_VERSION ?= $(shell $(GO_CMD) list -m -f "{{.Version}}" sigs.k8s.io/kueue)
KUEUE_IMAGE := $(K8S_REGISTRY)/kueue/kueue:$(KUEUE_VERSION)

JOBSET_VERSION ?= $(shell $(GO_CMD) list -m -f "{{.Version}}" sigs.k8s.io/jobset)
JOBSET_IMAGE := $(K8S_REGISTRY)/jobset/jobset:$(JOBSET_VERSION)

# Versions for external controllers
EXTERNAL_CRDS_DIR ?= dep-crds

KUEUE_ROOT = $(shell $(GO_CMD) list -m -mod=readonly -f "{{.Dir}}" sigs.k8s.io/kueue)
JOBSET_ROOT = $(shell $(GO_CMD) list -m -mod=readonly -f "{{.Dir}}" sigs.k8s.io/jobset)

.PHONY: gomod-download
gomod-download:
	$(GO_CMD) mod download

.PHONY: kind
kind: ## Download kind locally if necessary.
	@GOBIN=$(BIN_DIR) GO111MODULE=on $(GO_CMD) install sigs.k8s.io/kind@$(KIND_VERSION)

.PHONY: kustomize
kustomize: ## Download kustomize locally if necessary.
	@GOBIN=$(BIN_DIR) GO111MODULE=on $(GO_CMD) install sigs.k8s.io/kustomize/kustomize/v5@$(KUSTOMIZE_VERSION)

.PHONY: ginkgo
ginkgo: ## Download ginkgo locally if necessary.
	@GOBIN=$(BIN_DIR) GO111MODULE=on $(GO_CMD) install github.com/onsi/ginkgo/v2/ginkgo@$(GINKGO_VERSION)

.PHONY: controller-gen
controller-gen: ## Download controller-gen locally if necessary.
	@GOBIN=$(BIN_DIR) GO111MODULE=on $(GO_CMD) install sigs.k8s.io/controller-tools/cmd/controller-gen@$(CONTROLLER_GEN_VERSION)

.PHONY: setup-envtest
setup-envtest: envtest ## Download the binaries required for ENVTEST in the local bin directory.
	@echo "Setting up envtest binaries for Kubernetes version $(ENVTEST_K8S_VERSION)..."
	@$(ENVTEST) use $(ENVTEST_K8S_VERSION) --bin-dir $(BIN_DIR) -p path || { \
		echo "Error: Failed to set up envtest binaries for version $(ENVTEST_K8S_VERSION)."; \
		exit 1; \
	}

.PHONY: envtest
envtest: ## Download envtest-setup locally if necessary.
	@GOBIN=$(BIN_DIR) GO111MODULE=on $(GO_CMD) install sigs.k8s.io/controller-runtime/tools/setup-envtest@$(ENVTEST_VERSION)

.PHONY: golangci-lint
golangci-lint: ## Download golangci-lint locally if necessary.
	@GOBIN=$(BIN_DIR) GO111MODULE=on $(GO_CMD) install github.com/golangci/golangci-lint/v2/cmd/golangci-lint@$(GOLANGCI_LINT_VERSION)

.PHONY: yq
yq: ## Download yq locally if necessary.
	@GOBIN=$(BIN_DIR) GO111MODULE=on $(GO_CMD) install github.com/mikefarah/yq/v4@$(YQ_VERSION)

##@ External CRDs
.PHONY: kueue-operator-crd
kueue-operator-crd: ## Copy the CRDs from the kueue-operator to the dep-crds directory.
	if [ -d "$(EXTERNAL_CRDS_DIR)/kueue-operator" ]; then \
		chmod -R u+w "$(EXTERNAL_CRDS_DIR)/kueue-operator" && \
		rm -rf "$(EXTERNAL_CRDS_DIR)/kueue-operator"; \
	fi
	mkdir -p $(EXTERNAL_CRDS_DIR)/kueue-operator/
	cp -R -f $(KUEUE_ROOT)/config $(EXTERNAL_CRDS_DIR)/kueue-operator
	cd "$(EXTERNAL_CRDS_DIR)/kueue-operator/config/components/manager" && \
		chmod u+w kustomization.yaml && \
		$(KUSTOMIZE) edit set image controller=$(KUEUE_IMAGE) && \
		chmod u-w kustomization.yaml

.PHONY: jobset-operator-crd
jobset-operator-crd: ## Copy the CRDs from the jobset-operator to the dep-crds directory.
	if [ -d "$(EXTERNAL_CRDS_DIR)/jobset-operator" ]; then \
		chmod -R u+w "$(EXTERNAL_CRDS_DIR)/jobset-operator" && \
		rm -rf "$(EXTERNAL_CRDS_DIR)/jobset-operator"; \
	fi
	mkdir -p $(EXTERNAL_CRDS_DIR)/jobset-operator/
	cp -R -f $(JOBSET_ROOT)/config $(EXTERNAL_CRDS_DIR)/jobset-operator
	cd "$(EXTERNAL_CRDS_DIR)/jobset-operator/config/components/manager" && \
		chmod u+w kustomization.yaml && \
		$(KUSTOMIZE) edit set image controller=$(JOBSET_IMAGE) && \
		chmod u-w kustomization.yaml

.PHONY: dep-crds
dep-crds: gomod-download kueue-operator-crd jobset-operator-crd
	@echo "Copying CRDs from external operators to dep-crds directory"
