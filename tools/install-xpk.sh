#/bin/bash

set -e

curl -Lo /usr/local/bin/kubectl-kueue https://github.com/kubernetes-sigs/kueue/releases/download/v0.14.3/kubectl-kueue-linux-amd64

chmod +x /usr/local/bin/kubectl-kueue
