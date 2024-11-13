KUEUE_REPO=https://github.com/kubernetes-sigs/kueue.git
KUEUE_TMP_PATH=/tmp/xpk_tmp/kueue

KUBECTL_VERSION := $(shell curl -L -s https://dl.k8s.io/release/stable.txt)
OS := $(shell dpkg --print-architecture)

ifeq ($(OS),amd64)
	KUBECTL_URL = "https://dl.k8s.io/release/$(KUBECTL_VERSION)/bin/linux/amd64/kubectl"
endif
ifeq ($(OS),arm)
	KUBECTL_URL = "https://dl.k8s.io/release/$(KUBECTL_VERSION)/bin/linux/arm64/kubectl"
endif	

PROJECT_DIR := $(shell dirname $(abspath $(lastword $(MAKEFILE_LIST))))

BIN_PATH=$(PROJECT_DIR)/bin

.PHONY: install install_kjob install_kueuectl install_gcloud check_python update-path

install: check-python check-gcloud install-kubectl install-kueuectl install-kjob pip-install

pip-install:
	pip install .

install-kjob: install-kubectl
	git clone $(KUEUE_REPO) $(KUEUE_TMP_PATH)
	make -C $(KUEUE_TMP_PATH)/cmd/experimental/kjobctl kubectl-kjob
	mv $(KUEUE_TMP_PATH)/cmd/experimental/kjobctl/bin/kubectl-kjob $(BIN_PATH)/kubectl-kjob
	rm -rf $(KUEUE_TMP_PATH)

install-kubectl:
	curl -LO $(KUBECTL_URL)
	chmod +x kubectl
	mv ./kubectl $(BIN_PATH)/kubectl

install-kueuectl: install-kubectl
	git clone $(KUEUE_REPO) $(KUEUE_TMP_PATH)
	make -C $(KUEUE_TMP_PATH) kueuectl
	mv $(KUEUE_TMP_PATH)/bin/kubectl-kueue $(BIN_PATH)/kubectl-kueue
	rm -rf $(KUEUE_TMP_PATH)

check-gcloud:
	gcloud version || (echo "gcloud not installed, use this link to install: https://cloud.google.com/sdk/docs/install" && exit 1)

check-python:
	python3 --version || (echo "python3 not installed. Please install python in version required by xpk" && exit 1)
