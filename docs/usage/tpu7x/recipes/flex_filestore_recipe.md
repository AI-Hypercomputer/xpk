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

# Run training workload with Ironwood with flex-start using Filestore storage

## Create a cluster with flex-start provisioning

### Before you begin

Before you start, complete the following steps:

* Ensure you have a Google Cloud project with billing enabled.
* Get access to TPU7x. For more information, contact your account team.
* Ensure the account you're using with XPK has the roles listed in the [XPK GitHub repository](https://github.com/AI-Hypercomputer/xpk/blob/main/docs/permissions.md).

### Create a single-NIC, single slice cluster

Currently flex start provisioning for Ironwood works only in single slice and multi-host or multi-slice and single host setups. More options will be added soon

1. Set the following environment variables:

    > **NOTE:** For multi-host provisioning use an ACCELERATOR_TYPE with any topology that results to more than 8 chips, e.g. `tpu7x-2x2x2` or `tpu7x-16`. For single-host provisioning use an ACCELERATOR_TYPE with any topology that results to 8 or less chips, e.g. `tpu7x-2x2x1` or `tpu7x-8`.

    > **NOTE:** Single-host provisioning is not supported for single-slice. If you want to create a single-host cluster, you need to set `--num-slices` to 2 or higher on the `xpk cluster create` command.

    ```shell
    export PROJECT_ID=<project_id> # Your GCP project name
    export ZONE=<zone> # Example: us-central1-c
    export CLUSTER_NAME=<cluster_name> # Your cluster name
    # For a list of supported topologies, see: https://docs.cloud.google.com/tpu/docs/tpu/docs/tpu7x#configurations
    export ACCELERATOR_TYPE=<tpu_type> # Example:tpu7x-2x2x2
    ```

1. Set up your network configuration.

    ```shell
    export NETWORK_NAME=<network_name> # Your network name
    export SUBNET_NAME=<subnet_name> # Your subnet name
    export NETWORK_FW_NAME=${NETWORK_NAME}-privatefirewall # Your firewall name
    export IP_RANGE=<ip_range> # Your IP range in CIDR notation, e.g. 10.0.0.0/24
    export REGION=${ZONE%-*}
    gcloud compute networks create ${NETWORK_NAME} --mtu=8896 --project=${PROJECT_ID} \
        --subnet-mode=custom --bgp-routing-mode=regional
    gcloud compute networks subnets create ${SUBNET_NAME} --project=${PROJECT_ID} \
        --network=${NETWORK_NAME} --region=${REGION} --range=${IP_RANGE}
    gcloud compute firewall-rules create ${NETWORK_FW_NAME} --network=${NETWORK_NAME} \
        --allow tcp,icmp,udp --project=${PROJECT_ID}
    ```

1. Populate the `${CLUSTER_ARGUMENTS}` variable, which you'll use in the `xpk cluster create` command:

    ```shell
    export CLUSTER_ARGUMENTS="--network=${NETWORK_NAME} --subnetwork=${SUBNET_NAME}"
    ```

1. Create your GKE cluster with TPU7x node pools using the `xpk cluster create` command:

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
    # Your selected start time for the maintenance exclusion in
    # `YYYY-MM-DDTHH:MM:SSZ` format, e.g. "2025-11-24T00:00:00Z"
    export EXCLUSION_START_TIME=<exclusion_start_time>
    # Your selected end time for the maintenance exclusion in
    # `YYYY-MM-DDTHH:MM:SSZ` format, e.g. "2025-12-24T00:00:00Z"
    export EXCLUSION_END_TIME=<exclusion_end_time>
    ```

    ```shell
    gcloud container clusters update ${CLUSTER_NAME} \
        --region=${REGION} \
        --project=${PROJECT_ID} \
        --add-maintenance-exclusion-name="no-upgrade-next-month" \
        --add-maintenance-exclusion-start="${EXCLUSION_START_TIME}" \
        --add-maintenance-exclusion-end="${EXCLUSION_END_TIME}" \
        --add-maintenance-exclusion-scope="no_upgrades"
    ```

1. Create a Filestore storage by running the commands below:

    ```shell
    export STORAGE_NAME=<storage_name> # Your storage name
    xpk storage create ${STORAGE_NAME} --type=gcpfilestore \
      --auto-mount=false --mount-point=/data-fs --readonly=false \
      --size=1024 --tier=BASIC_HDD --vol=default \
      --project=${PROJECT_ID} --cluster=${CLUSTER_NAME} --zone=${ZONE}
    ```

1. Attach the Filestore storage to your cluster by running the commands below:

    ```shell
    export BASE_OUTPUT_DIR="/data-fs"
    xpk storage attach ${STORAGE_NAME} --cluster=${CLUSTER_NAME} --zone=${ZONE} \
      --project=${PROJECT_ID} --type=gcpfilestore   --auto-mount=true \
      --vol=default --mount-point=/data-fs --readonly=false
    ```

1. Download mock tensorflow training script

    ```shell
    curl -o tensorflow.py https://raw.githubusercontent.com/AI-Hypercomputer/xpk/refs/heads/main/examples/tensorflow.py
    ```


1. Run a mock tensorflow training workload on the cluster.

    ```shell
    xpk workload create \
        --cluster ${CLUSTER_NAME} \
        --workload tf-mock-$(date +%H%M) \
        --tpu-type=${ACCELERATOR_TYPE} \
        --zone ${ZONE} \
        --project ${PROJECT_ID} \
        --command "python3 tensorflow.py"
    ```
