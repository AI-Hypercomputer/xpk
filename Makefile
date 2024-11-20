KUEUE_REPO=https://github.com/kubernetes-sigs/kueue.git
KUEUE_TMP_PATH=/tmp/xpk_tmp/kueue

KUBECTL_VERSION := $(shell curl -L -s https://dl.k8s.io/release/stable.txt)
KUEUE_VERSION=v0.8.4

PLATFORM := $(shell dpkg --print-architecture)

KUBECTL_URL = "https://dl.k8s.io/release/$(KUBECTL_VERSION)/bin/linux/$(PLATFORM)/kubectl"
KUEUECTL_URL = "https://github.com/kubernetes-sigs/kueue/releases/download/$(KUEUE_VERSION)/kubectl-kueue-linux-$(PLATFORM)"

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
	git clone --depth 1 --branch $(KUEUE_VERSION) $(KUEUE_REPO) $(KUEUE_TMP_PATH)
	make -C $(KUEUE_TMP_PATH)/cmd/experimental/kjobctl kubectl-kjob
	mv $(KUEUE_TMP_PATH)/cmd/experimental/kjobctl/bin/kubectl-kjob $(BIN_PATH)/kubectl-kjob
	rm -rf $(KUEUE_TMP_PATH)

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
