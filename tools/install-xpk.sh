#/bin/bash

set -e

curl -Lo /usr/local/bin/kubectl-kueue https://github.com/kubernetes-sigs/kueue/releases/download/v0.14.3/kubectl-kueue-linux-amd64

chmod +x /usr/local/bin/kubectl-kueue

curl -Lo /usr/local/bin/kubectl-kjob https://github.com/kubernetes-sigs/kjob/releases/download/v0.1.0/kubectl-kjob-linux-amd64

chmod +x /usr/local/bin/kubectl-kjob
