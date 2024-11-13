KUEUE_REPO=https://github.com/kubernetes-sigs/kueue.git
KUEUE_TMP_PATH=/tmp/xpk_tmp/kueue

KUBECTL_VERSION := $(shell curl -L -s https://dl.k8s.io/release/stable.txt)

KUBECTL_AMD64="https://dl.k8s.io/release/$(KUBECTL_VERSION)/bin/linux/amd64/kubectl"
KUBECTL_ARM="https://dl.k8s.io/release/$(KUBECTL_VERSION)/bin/linux/arm64/kubectl"

OS := $(shell dpkg --print-architecture)

.PHONY: install install_kjob install_kueuectl install_gcloud check_python

install: install_kjob
	pip install .

install_kjob: install_kueuectl
	git clone $(KUEUE_REPO) $(KUEUE_TMP_PATH)
	make -C $(KUEUE_TMP_PATH)/cmd/experimental/kjobctl kubectl-kjob
	mv $(KUEUE_TMP_PATH)/cmd/experimental/kjobctl/bin/kubectl-kjob ~/.local/bin/kubectl-kjob
	rm -rf $(KUEUE_TMP_PATH)

install_kubectl: check_gcloud
ifeq ($(OS),amd64)
	curl -LO $(KUBECTL_AMD64)
endif
ifeq ($(OS),arm)
	curl -LO $(KUBECTL_ARM)
endif	
	chmod +x kubectl
	mkdir -p ~/.local/bin
	mv ./kubectl ~/.local/bin/kubectl

install_kueuectl: install_kubectl
	git clone $(KUEUE_REPO) $(KUEUE_TMP_PATH)
	make -C $(KUEUE_TMP_PATH) kueuectl
	mv $(KUEUE_TMP_PATH)/bin/kubectl-kueue ~/.local/bin/kubectl-kueue
	rm -rf $(KUEUE_TMP_PATH)

check_gcloud: check_python
	gcloud version || (echo "gcloud not installed, use this link to install: https://cloud.google.com/sdk/docs/install" && exit 1)

check_python:
	python3 --version || (echo "python3 not installed. Please install python in version required by xpk" && exit 1)
