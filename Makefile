OS := $(shell uname -s | tr A-Z a-z)
ARCH := $(shell uname -m)
PLATFORM := $(shell uname -m | sed -e 's/aarch64/arm64/' | sed -e 's/x86_64/amd64/')

KUEUE_VERSION=v0.15.2
GO_CONTAINERREGISTRY_VERSION=v0.20.7
KUEUECTL_URL = "https://github.com/kubernetes-sigs/kueue/releases/download/$(KUEUE_VERSION)/kubectl-kueue-$(OS)-$(PLATFORM)"
GO_CONTAINERREGISTRY_URL = "https://github.com/google/go-containerregistry/releases/download/$(GO_CONTAINERREGISTRY_VERSION)/go-containerregistry_$(OS)_$(ARCH).tar.gz"

PROJECT_DIR := $(realpath $(shell dirname $(firstword $(MAKEFILE_LIST))))
BIN_PATH=$(PROJECT_DIR)/bin
PIP_OPTS ?=

.PHONY: install
install: check-python check-gcloud install-gcloud-auth-plugin install-kueuectl pip-install

.PHONY: install-dev
install-dev: check-python check-gcloud mkdir-bin install-kueuectl pip-install pip-install-dev install-pytest install-lint

.PHONY: pip-install-dev
pip-install-dev:
	pip install $(PIP_OPTS) -e ".[dev]"

.PHONY: pip-install
pip-install:
	pip install $(PIP_OPTS) -e .

.PHONY: install-pytest
install-pytest:
	pip install -U pytest

.PHONY: run-unittests
run-unittests:
	XPK_TESTER=false XPK_VERSION_OVERRIDE=v0.0.0 pytest  -vv src/xpk/

.PHONY: goldens
goldens:
	XPK_TESTER=false XPK_VERSION_OVERRIDE=v0.0.0 python3 tools/recipes.py update recipes/*.md

.PHONY: verify-goldens
verify-goldens:
	XPK_TESTER=false XPK_VERSION_OVERRIDE=v0.0.0 UPDATE_GOLDEN_COMMAND="make goldens" python3 tools/recipes.py golden recipes/*.md

.PHONY: mkdir-bin
mkdir-bin:
	mkdir -p $(BIN_PATH)

.PHONY: install-kueuectl
install-kueuectl: mkdir-bin
	curl -Lo $(BIN_PATH)/kubectl-kueue $(KUEUECTL_URL);
	chmod +x $(BIN_PATH)/kubectl-kueue;

.PHONY: install-crane
install-crane: mkdir-bin
	curl -Lo go-containerregistry.tar.gz $(GO_CONTAINERREGISTRY_URL);
	tar -zxvf go-containerregistry.tar.gz -C $(BIN_PATH)/ crane
	rm go-containerregistry.tar.gz
	chmod +x $(BIN_PATH)/crane;

.PHONY: install-gcloud-auth-plugin
install-gcloud-auth-plugin:
	chmod +x tools/install-gke-auth-plugin.sh
	./tools/install-gke-auth-plugin.sh

.PHONY: check-gcloud
check-gcloud:
	gcloud version || (echo "gcloud not installed, use this link to install: https://cloud.google.com/sdk/docs/install" && exit 1)

.PHONY: check-python
check-python:
	python3 --version || (echo "python3 not installed. Please install python in version required by xpk" && exit 1)

.PHONY: install-lint
install-lint: install-mypy install-pyink install-pylint pip-install

.PHONY: install-mypy
install-mypy:
	pip install mypy~=1.17 types-PyYAML==6.0.2 types-docker~=7.1.0.0

.PHONY: install-pyink
install-pyink:
	pip install pyink==24.3.0

.PHONY: install-pylint
install-pylint:
	pip install pylint

.PHONY: verify
verify: pylint pyink mypy

.PHONY: pylint
pylint:
	pylint $(shell git ls-files '*.py')

.PHONY: pyink
pyink:
	pyink --check .

.PHONY: pyink-fix
pyink-fix:
	pyink .

.PHONY: mypy
mypy:
	mypy
