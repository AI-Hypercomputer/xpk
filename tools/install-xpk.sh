#/bin/bash

set -e

pip install --upgrade xpk

curl -Lo /usr/local/bin/kubectl-kueue https://github.com/kubernetes-sigs/kueue/releases/download/v0.12.2/kubectl-kueue-linux-amd64

chmod +x /usr/local/bin/kubectl-kueue

curl -Lo /usr/local/bin/kubectl-kjob https://github.com/kubernetes-sigs/kjob/releases/download/v0.1.0/kubectl-kjob-linux-amd64

chmod +x /usr/local/bin/kubectl-kjob
