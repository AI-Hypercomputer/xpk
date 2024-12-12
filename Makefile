KUEUE_REPO=https://github.com/kubernetes-sigs/kueue.git
KUEUE_TMP_PATH=/tmp/xpk_tmp/kueue

KUBECTL_VERSION := $(shell curl -L -s https://dl.k8s.io/release/stable.txt)
KUEUE_VERSION=v0.9.1

OS := $(shell uname -s | tr A-Z a-z)
PLATFORM := $(shell uname -m | sed -e 's/aarch64/arm64/' | sed -e 's/x86_64/amd64/')

KUBECTL_URL = "https://dl.k8s.io/release/$(KUBECTL_VERSION)/bin/$(OS)/$(PLATFORM)/kubectl"
KUEUECTL_URL = "https://github.com/kubernetes-sigs/kueue/releases/download/$(KUEUE_VERSION)/kubectl-kueue-$(OS)-$(PLATFORM)"

PROJECT_DIR := $(realpath $(shell dirname $(firstword $(MAKEFILE_LIST))))

BIN_PATH=$(PROJECT_DIR)/bin

.PHONY: install
install: check-python check-gcloud install-kueuectl install-kjob pip-install

.PHONY: install-dev
install-dev: check-python check-gcloud mkdir-bin install-kubectl install-kueuectl install-kjob pip-install install-pytest

.PHONY: pip-install
pip-install:
	pip install .

.PHONY: install-pytest
install-pytest:
	pip install -U pytest

.PHONY: run-unittests
run-unittests:
	pytest src/xpk/

.PHONY: install-kjob
install-kjob: install-kubectl
	git clone --depth 1 --branch $(KUEUE_VERSION) $(KUEUE_REPO) $(KUEUE_TMP_PATH)
	make -C $(KUEUE_TMP_PATH)/cmd/experimental/kjobctl kubectl-kjob
	mv $(KUEUE_TMP_PATH)/cmd/experimental/kjobctl/bin/kubectl-kjob $(BIN_PATH)/kubectl-kjob
	rm -rf $(KUEUE_TMP_PATH)

.PHONY: mkdir-bin
mkdir-bin:
	mkdir -p $(BIN_PATH)

.PHONY: install-kubectl
install-kubectl: mkdir-bin
	curl -Lo $(BIN_PATH)/kubectl $(KUBECTL_URL)
	chmod +x $(BIN_PATH)/kubectl

.PHONY: install-kueuectl
install-kueuectl: install-kubectl
	curl -Lo $(BIN_PATH)/kubectl-kueue $(KUEUECTL_URL)
	chmod +x $(BIN_PATH)/kubectl-kueue

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
