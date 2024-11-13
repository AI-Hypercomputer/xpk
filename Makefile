KUEUE_REPO=https://github.com/kubernetes-sigs/kueue.git
KUEUE_TMP_PATH=/tmp/xpk_tmp/kueue


.PHONY: install install_kjob install_kueuectl install_gcloud check_python

install: install_kjob
	pip install .

install_kjob: install_kueuectl
	git clone $(KUEUE_REPO) $(KUEUE_TMP_PATH)
	make -C $(KUEUE_TMP_PATH)/cmd/experimental/kjobctl kubectl-kjob
	sudo mv $(KUEUE_TMP_PATH)/cmd/experimental/kjobctl/bin/kubectl-kjob /usr/local/bin/kubectl-kjob
	rm -rf $(KUEUE_TMP_PATH)

install_kubectl: check_gcloud
	curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl"
	chmod +x kubectl
	mkdir -p ~/.local/bin
	mv ./kubectl ~/.local/bin/kubectl

install_kueuectl: install_kubectl
	git clone $(KUEUE_REPO) $(KUEUE_TMP_PATH)
	make -C $(KUEUE_TMP_PATH) kueuectl
	sudo mv $(KUEUE_TMP_PATH)/bin/kubectl-kueue /usr/local/bin/kubectl-kueue
	rm -rf $(KUEUE_TMP_PATH)

check_gcloud: check_python
	gcloud version || (echo "gcloud not installed, use this link to install: https://cloud.google.com/sdk/docs/install" && exit 1)

check_python:
	python3 --version || (echo "python3 not installed. Please install python in version required by xpk" && exit 1)
