<!--
 Copyright 2025 Google LLC

 Licensed under the Apache License, Version 2.0 (the "License");
 you may not use this file except in compliance with the License.
 You may obtain a copy of the License at

      https://www.apache.org/licenses/LICENSE-2.0

 Unless required by applicable law or agreed to in writing, software
 distributed under the License is distributed on an "AS IS" BASIS,
 WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 See the License for the specific language governing permissions and
 limitations under the License.
 -->

# Flex and Lustre recipe

## Cluster Create with flex provisioning

1. Set the following environment variables:

    > **NOTE:** For single-host provisioning use an ACCELARATOR_TYPE with any topology that results to 8 or less chips, e.g. tpu7x-2x2x1 or tpu7x-8. For multi-host provisioning use an ACCELARATOR_TYPE with any topology that results to more than 8 chips, e.g. tpu7x-2x2x2 or tpu7x-16.

    ```shell
    export PROJECT_ID=<project_id> # Your GCP project name
    export ZONE=<zone> # Example: us-central1-c
    export CLUSTER_NAME=<cluster_name> # Your cluster name
    export ACCELERATOR_TYPE=<tpu_type> # Example:tpu7x-4x4x8, For a list of supported topologies, see [Supported configurations](/tpu/docs/tpu7x#configurations)
    ```

1. Follow the instructions in the [Configure MTU](https://docs.cloud.google.com/tpu/docs/v6e-training#configure_mtu) section to optimize your network configuration.

1. Populate the `${CLUSTER_ARGUMENTS}` variable, which you'll use in the `xpk cluster create` command:

    ```shell
    export CLUSTER_ARGUMENTS="--network=${NETWORK_NAME} --subnetwork=${SUBNET_NAME}"
    ```

1. Create your {{gke_name_short}} cluster with TPU7x node pools using the `xpk cluster create` command:

    ```shell
    xpk cluster create \
        --project=${PROJECT_ID} \
        --zone=${ZONE} \
        --cluster ${CLUSTER_NAME} \
        --cluster-cpu-machine-type=n1-standard-8 \
        --tpu-type=${ACCELERATOR_TYPE} \
        --flex \
        --custom-cluster-arguments="${CLUSTER_ARGUMENTS}"
    ```

    Setting the `--cluster-cpu-machine-type` flag to `n1-standard-8` (or larger)
    ensures that the default node pool has sufficient CPU for system pods, for
    example [JobSet](https://jobset.sigs.k8s.io/docs/installation/) webhook,
    preventing [errors](https://jobset.sigs.k8s.io/docs/troubleshooting/#1-webhook-not-available-error-when-attempting-to-create-a-jobset).
    By default, XPK uses `e2-standard-16`. Some zones only support specific CPU
    types, so you might need to change between `n1`, `n2`, and `e2` types.
    Otherwise, you might encounter [quota errors](https://github.com/google/xpk/blob/main/README.md#invalid-machine-type-for-cpus).

1. Add a maintenance exclusion to prevent upgrades for the cluster:

    ```shell
    export EXCLUSION_START_TIME=<exclusion_start_time> # Your selected start time for the maintenance exclusion in `YYYY-MM-DDTHH:MM:SSZ` format, e.g. "2025-11-24T00:00:00Z"
    export EXCLUSION_END_TIME=<exclusion_end_time> # Your selected end time for the maintenance exclusion in `YYYY-MM-DDTHH:MM:SSZ` format, e.g. "2025-12-24T00:00:00Z"
    ```

    ```shell
    gcloud container clusters update ${CLUSTER_NAME} \
        --zone=${ZONE} \
        --add-maintenance-exclusion-name="no-upgrade-next-month" \
        --add-maintenance-exclusion-start="${EXCLUSION_START_TIME}" \
        --add-maintenance-exclusion-end="${EXCLUSION_END_TIME}" \
        --add-maintenance-exclusion-scope="no_upgrades"
    ```
