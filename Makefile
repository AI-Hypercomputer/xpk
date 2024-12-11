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

.PHONY: install install_kjob install_kueuectl install_gcloud check_python update-path 

install: check-python check-gcloud install-kueuectl install-kjob pip-install

install-dev: check-python check-gcloud mkdir-bin install-kubectl install-kueuectl install-kjob pip-install install-pytest 

pip-install:
	pip install .

install-pytest:
	pip install -U pytest

run-unittests:
	pytest src/xpk/

install-kjob: install-kubectl
	git clone --depth 1 --branch $(KUEUE_VERSION) $(KUEUE_REPO)
	make -C kueue/cmd/experimental/kjobctl kubectl-kjob
	export PATH=$(BIN_PATH):$(PATH)

mkdir-bin:
	mkdir -p $(BIN_PATH)

install-kubectl: mkdir-bin
	curl -Lo $(BIN_PATH)/kubectl $(KUBECTL_URL)
	chmod +x $(BIN_PATH)/kubectl

install-kueuectl: install-kubectl
	curl -Lo $(BIN_PATH)/kubectl-kueue $(KUEUECTL_URL)
	chmod +x $(BIN_PATH)/kubectl-kueue

check-gcloud:
	gcloud version || (echo "gcloud not installed, use this link to install: https://cloud.google.com/sdk/docs/install" && exit 1)

check-python:
	python3 --version || (echo "python3 not installed. Please install python in version required by xpk" && exit 1)
