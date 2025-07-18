KUEUE_REPO=https://github.com/kubernetes-sigs/kueue.git

KUBECTL_VERSION := $(shell curl -L -s https://dl.k8s.io/release/stable.txt)
KUEUE_VERSION=v0.12.2
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

.PHONY: install
install: check-python check-gcloud install-gcloud-auth-plugin install-kueuectl install-kjobctl pip-install

.PHONY: install-dev
install-dev: check-python check-gcloud mkdir-bin install-kueuectl install-kjobctl pip-install install-pytest

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
	curl -Lo $(BIN_PATH)/kubectl-kueue $(KUEUECTL_URL);
	chmod +x $(BIN_PATH)/kubectl-kueue;

.PHONY: install-kjobctl
install-kjobctl: mkdir-bin
	#curl -Lo $(BIN_PATH)/kubectl-kjob $(KJOBCTL_URL)
	#chmod +x $(BIN_PATH)/kubectl-kjob
	# TODO: Switch to kjob release-based installation once version >=0.2.0 is available.
	docker build -f tools/Dockerfile-kjob -t $(KJOB_DOCKER_IMG) tools/;
	docker run -idt --name $(KJOB_DOCKER_CONTAINER) $(KJOB_DOCKER_IMG);
	docker cp $(KJOB_DOCKER_CONTAINER):/kjob/bin/kubectl-kjob $(BIN_PATH)/kubectl-kjob;
	docker rm -f $(KJOB_DOCKER_CONTAINER);
	docker image rm $(KJOB_DOCKER_IMG);

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
