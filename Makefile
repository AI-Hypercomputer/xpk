KUEUE_REPO=https://github.com/kubernetes-sigs/kueue.git

KUBECTL_VERSION := $(shell curl -L -s https://dl.k8s.io/release/stable.txt)
KUEUE_VERSION=v0.10.0
KJOB_VERSION=v0.1.0

OS := $(shell uname -s | tr A-Z a-z)
PLATFORM := $(shell uname -m | sed -e 's/aarch64/arm64/' | sed -e 's/x86_64/amd64/')

KUBECTL_URL = "https://dl.k8s.io/release/$(KUBECTL_VERSION)/bin/$(OS)/$(PLATFORM)/kubectl"
KUEUECTL_URL = "https://github.com/kubernetes-sigs/kueue/releases/download/$(KUEUE_VERSION)/kubectl-kueue-$(OS)-$(PLATFORM)"
KJOBCTL_URL = "https://github.com/kubernetes-sigs/kjob/releases/download/$(KJOB_VERSION)/kubectl-kjob-$(OS)-$(PLATFORM)"

PROJECT_DIR := $(realpath $(shell dirname $(firstword $(MAKEFILE_LIST))))
KJOB_DOCKER_IMG := xpk_kjob
KJOB_DOCKER_CONTAINER := xpk_kjob_container
BIN_PATH=$(PROJECT_DIR)/bin

GIT_COMMIT_HASH := $(shell git rev-parse HEAD)

.PHONY: install
install: save-git-hash check-python check-gcloud install-kueuectl install-kjobctl pip-install

.PHONY: install-dev
install-dev: save-git-hash check-python check-gcloud mkdir-bin install-kueuectl install-kjobctl pip-install install-pytest

.PHONY: save-git-hash
save-git-hash:
	sed -i -e "s/__git_commit_hash__ = .*/__git_commit_hash__ = '${GIT_COMMIT_HASH}'/" src/xpk/core/core.py

.PHONY: pip-install
pip-install:
	pip install .

.PHONY: install-pytest
install-pytest:
	pip install -U pytest

.PHONY: run-unittests
run-unittests:
	pytest  -vv src/xpk/core/tests/unit/

run-integrationtests:
	pytest src/xpk/core/tests/integration/

.PHONY: mkdir-bin
mkdir-bin:
	mkdir -p $(BIN_PATH)

.PHONY: install-kueuectl
install-kueuectl: mkdir-bin
	curl -Lo $(BIN_PATH)/kubectl-kueue $(KUEUECTL_URL)
	chmod +x $(BIN_PATH)/kubectl-kueue

.PHONY: install-kjobctl
install-kjobctl: mkdir-bin
	curl -Lo $(BIN_PATH)/kubectl-kjob $(KJOBCTL_URL)
	chmod +x $(BIN_PATH)/kubectl-kjob

.PHONY: check-gcloud
check-gcloud:
	gcloud version || (echo "gcloud not installed, use this link to install: https://cloud.google.com/sdk/docs/install" && exit 1)

.PHONY: check-python
check-python:
	python3 --version || (echo "python3 not installed. Please install python in version required by xpk" && exit 1)

.PHONY: install-lint
install-lint: install-pytype install-pyink install-pylint pip-install

.PHONY: install-pytype
install-pytype:
	pip install pytype

.PHONY: install-pyink
install-pyink:
	pip install pyink==24.3.0

.PHONY: install-pylint
install-pylint:
	pip install pylint

.PHONY: verify
verify: install-lint pylint pyink pytype

.PHONY: pylint
pylint:
	pylint $(shell git ls-files '*.py')

.PHONY: pyink
pyink:
	pyink --check .

.PHONY: pyink-fix
pyink-fix:
	pyink .

.PHONY: pytype
pytype:
	pytype --config=pytype-conf.cfg
