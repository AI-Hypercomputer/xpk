#!/usr/bin/env bash

# Copyright 2025 The Kubernetes Authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

export KUSTOMIZE="$ROOT_DIR"/bin/kustomize
export GINKGO="$ROOT_DIR"/bin/ginkgo
export KIND="$ROOT_DIR"/bin/kind
export YQ="$ROOT_DIR"/bin/yq
export DEFAULT_SLICE_NAMESPACE="slice-controller-system"
export SLICE_NAMESPACE="${SLICE_NAMESPACE:-${DEFAULT_SLICE_NAMESPACE}}"

export KIND_VERSION="${E2E_KIND_VERSION/"kindest/node:v"/}"

export KUEUE_MANIFEST="${ROOT_DIR}/test/e2e/config/kueue"
export JOBSET_MANIFEST="${ROOT_DIR}/${EXTERNAL_CRDS_DIR}/jobset-operator/config/default"

# agnhost image to use for testing.
export E2E_TEST_AGNHOST_IMAGE=registry.k8s.io/e2e-test-images/agnhost:2.56@sha256:352a050380078cb2a1c246357a0dfa2fcf243ee416b92ff28b44a01d1b4b0294
E2E_TEST_AGNHOST_IMAGE_WITHOUT_SHA=${E2E_TEST_AGNHOST_IMAGE%%@*}


# $1 cluster name
# $2 kubeconfig
function cluster_cleanup {
    kubectl config --kubeconfig="$2" use-context "kind-$1"

    $KIND export logs "$ARTIFACTS" --name "$1" || true
    kubectl describe pods --kubeconfig="$2" -n $DEFAULT_SLICE_NAMESPACE > "$ARTIFACTS/$1-$DEFAULT_SLICE_NAMESPACE-pods.log" || true
    kubectl describe pods --kubeconfig="$2" > "$ARTIFACTS/$1-default-pods.log" || true
    $KIND delete cluster --name "$1"
}

# $1 cluster name
# $2 cluster kind config
# $3 kubeconfig
function cluster_create {
    prepare_kubeconfig "$1" "$3"

    $KIND create cluster --name "$1" --image "$E2E_KIND_VERSION" --config "$2" --kubeconfig="$3" --wait 1m -v 5  > "$ARTIFACTS/$1-create.log" 2>&1 \
    ||  { echo "unable to start the $1 cluster "; cat "$ARTIFACTS/$1-create.log" ; }

    kubectl config --kubeconfig="$3" use-context "kind-$1"
    kubectl get nodes --kubeconfig="$3" > "$ARTIFACTS/$1-nodes.log" || true
    kubectl describe pods --kubeconfig="$3" -n kube-system > "$ARTIFACTS/$1-system-pods.log" || true
}

function prepare_docker_images {
    docker pull "$E2E_TEST_AGNHOST_IMAGE"

    # We can load image by a digest but we cannot reference it by the digest that we pulled.
    # For more information https://github.com/kubernetes-sigs/kind/issues/2394#issuecomment-888713831.
    # Manually create tag for image with digest which is already pulled
    docker tag $E2E_TEST_AGNHOST_IMAGE "$E2E_TEST_AGNHOST_IMAGE_WITHOUT_SHA"
    docker pull "${KUEUE_IMAGE}"
    docker pull "${JOBSET_IMAGE}"
}

# $1 cluster
function cluster_kind_load {
    cluster_kind_load_image "$1" "${E2E_TEST_AGNHOST_IMAGE_WITHOUT_SHA}"
    cluster_kind_load_image "$1" "$IMAGE_TAG"
}

# $1 cluster
# $2 kubeconfig
function kind_load {
    kubectl config --kubeconfig="$2" use-context "kind-$1"

    if [ "$CREATE_KIND_CLUSTER" == 'true' ]; then
	    cluster_kind_load "$1"
    fi

    install_jobset "$1" "$2"
    install_kueue "$1" "$2"
}

# $1 cluster
# $2 image
function cluster_kind_load_image {
    # check if the command to get worker nodes could succeeded
    if ! $KIND get nodes --name "$1" > /dev/null 2>&1; then
        echo "Failed to retrieve nodes for cluster '$1'."
        return 1
    fi
    # filter out 'control-plane' node, use only worker nodes to load image
    worker_nodes=$($KIND get nodes --name "$1" | grep -v 'control-plane' | paste -sd "," -)
    if [[ -n "$worker_nodes" ]]; then
        echo "kind load docker-image '$2' --name '$1' --nodes '$worker_nodes'"
        $KIND load docker-image "$2" --name "$1" --nodes "$worker_nodes"
    fi
}

# $1 kubeconfig
function cluster_slice_deploy {
    local initial_image
    initial_image=$($YQ '.images[] | select(.name == "controller") | [.newName, .newTag] | join(":")' config/manager/kustomization.yaml)
    (cd config/manager && $KUSTOMIZE edit set image controller="$IMAGE_TAG")

    local build_output
    build_output=$($KUSTOMIZE build "${ROOT_DIR}/config/dev")
    build_output="${build_output//$DEFAULT_SLICE_NAMESPACE/$SLICE_NAMESPACE}"
    echo "$build_output" | kubectl apply --kubeconfig="$1" --server-side -f -

    (cd "${ROOT_DIR}/config/manager" && $KUSTOMIZE edit set image controller="$initial_image")
}

# $1 cluster name
# $2 kubeconfig option
function install_kueue {
    cluster_kind_load_image "${1}" "${KUEUE_IMAGE}"
    kubectl apply --kubeconfig="$2" --server-side -k "${KUEUE_MANIFEST}"
}

# $1 cluster name
# $2 kubeconfig option
function install_jobset {
    cluster_kind_load_image "${1}" "${JOBSET_IMAGE}"
    kubectl apply --kubeconfig="$2" --server-side -k "${JOBSET_MANIFEST}"
}

# $1 cluster name
# $2 kubeconfig file path
function prepare_kubeconfig {
    local kind_name=$1
    local kubeconfig=$2
    if [[ "$kubeconfig" != "" ]]; then
        cat <<EOF > "$kubeconfig"
        apiVersion: v1
        kind: Config
        preferences: {}
EOF
        kubectl config --kubeconfig="$kubeconfig" set-context "kind-$kind_name" \
        --cluster="$kind_name" \
        --user="$kind_name"
    fi
}
