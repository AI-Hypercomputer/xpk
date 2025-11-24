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

# Run training workload with Ironwood and flex-start using Lustre storage

## Create a cluster with flex-start provisioning

### Before you begin

Before you start, complete the following steps:

* Make sure that you have XPK and its prerequisites installed by following instructions found [here](/docs/installation.md).
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
        --custom-cluster-arguments="${CLUSTER_ARGUMENTS}" \
        --enable-lustre-csi-driver
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

### Run a workload

<details>
<summary><strong>Option A: Mock training workload</strong></summary>

1. Download a fake training training script

    ```shell
    curl -o fake_training.py https://raw.githubusercontent.com/AI-Hypercomputer/xpk/refs/heads/main/examples/fake_training.py
    ```

1. Run a mock training workload on the cluster.

    ```shell
    xpk workload create \
        --cluster ${CLUSTER_NAME} \
        --workload tf-mock-$(date +%H%M) \
        --tpu-type=${ACCELERATOR_TYPE} \
        --zone ${ZONE} \
        --project ${PROJECT_ID} \
        --command "python3 fake_training.py"
    ```

</details>

<details>
<summary><strong>Option B: Training with MaxText</strong></summary>

1. Set up the networking needed for a Lustre storage by running the commands below:

    ```shell
    export IP_RANGE_NAME=<ip_range_name> # Your IP range name
    export FIREWALL_RULE_NAME=<fw_rule_name> # Your firewall rule name

    # a. enable service networking
    gcloud services enable servicenetworking.googleapis.com \
      --project=${PROJECT_ID}

    # b. Create an IP address range
    gcloud compute addresses create ${IP_RANGE_NAME} \
      --global \
      --purpose=VPC_PEERING \
      --prefix-length=20 \
      --description="Managed Lustre VPC Peering" \
      --network=${NETWORK_NAME} \
      --project=${PROJECT_ID}

    # c. Get the CIDR range of the IP address range
    CIDR_RANGE=$(
      gcloud compute addresses describe ${IP_RANGE_NAME} \
          --global  \
          --format="value[separator=/](address, prefixLength)" \
          --project=${PROJECT_ID}
    )

    # d. Create a firewall rule to allow TCP traffic from the IP address range
    gcloud compute firewall-rules create ${FIREWALL_RULE_NAME} \
        --allow=tcp:988,tcp:6988 \
        --network=${NETWORK_NAME} \
        --source-ranges=${CIDR_RANGE} \
        --project=${PROJECT_ID}

    # e. Connect the peering (required IAM role: compute.networkAdmin or servicenetworking.networksAdmin role)
    gcloud services vpc-peerings connect \
        --network=${NETWORK_NAME} \
        --project=${PROJECT_ID} \
        --ranges=${IP_RANGE_NAME} \
        --service=servicenetworking.googleapis.com
    ```

1. Create the Lustre storage by running the commands below:

    ```shell
    export STORAGE_NAME=<storage_name> # Your storage name
    export STORAGE_THROUGHPUT=1000
    export STORAGE_CAPACITY=18000
    export STORAGE_FS=lfs
    export LOCATION=${ZONE}

    gcloud lustre instances create ${STORAGE_NAME} \
      --per-unit-storage-throughput=${STORAGE_THROUGHPUT} \
      --capacity-gib=${STORAGE_CAPACITY} \
      --filesystem=${STORAGE_FS} \
      --location=${LOCATION} \
      --network=projects/${PROJECT_ID}/global/networks/${NETWORK_NAME} \
      --project=${PROJECT_ID} \
      --gke-support-enabled
    ```

1. Get Lustre properties. Note the mountPoint property.

    ```shell
    gcloud lustre instances describe konradkaim-lustre --location=us-central1-c
    ```

1. Prepare the Lustre manifest file, use the IP address part of the mountPoint from the command above.

    ```shell
    export VOLUME_IP=<volume_ip> # Should be equal to the mount point value from the previous command
    export VOLUME_HANDLE="${PROJECT_ID}/${ZONE}/${STORAGE_NAME}" # Your volume handle

    echo "apiVersion: v1
          kind: PersistentVolume
          metadata:
            name: xpk-lustre-pv
          spec:
            storageClassName: ""
            capacity:
              storage: 18000Gi
            accessModes:
              - ReadWriteMany
            persistentVolumeReclaimPolicy: Retain
            volumeMode: Filesystem
            claimRef:
              namespace: default
              name: xpk-lustre-pvc
            csi:
              driver: lustre.csi.storage.gke.io
              volumeHandle: ${VOLUME_HANDLE}
              volumeAttributes:
                ip: ${VOLUME_IP}
                filesystem: lfs
          ---
            kind: PersistentVolumeClaim
            apiVersion: v1
            metadata:
              name: xpk-lustre-pvc
            spec:
              accessModes:
                - ReadWriteMany
              storageClassName: ""
              volumeName: xpk-lustre-pv
              resources:
                requests:
                  storage: 18000Gi" > lustre-manifest-attach.yaml
    ```

1. Attach the Lustre storage to your cluster by running the commands below:

    ```shell
    export BASE_OUTPUT_DIR="/lustre-data"
    xpk storage attach ${STORAGE_NAME} \
      --cluster=${CLUSTER_NAME} --project=${PROJECT_ID} --zone=${LOCATION} \
      --type=lustre \
      --mount-point=$BASE_OUTPUT_DIR \
      --readonly=false \
      --auto-mount=true \
      --manifest='./lustre-manifest-attach.yaml'
    ```

1. Build or upload the MaxText Docker image.
    Note: MaxText supports **Python 3.12 only**. Build your virtual environment with
    3.12 to install the correct dependencies.

    You can either build a Docker image locally using scripts provided by
    [MaxText](https://github.com/AI-Hypercomputer/maxtext) or use a prebuilt image.
    The following commands copy your local directory into the container:

    ```shell
    # Make sure you're running on a virtual environment with python3.12. If nothing is printed, you have the correct version.
    [[ "$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null)" == "3.12" ]] || { >&2 echo "Error: Python version must be 3.12."; false; }
    ```

    ```shell
    # Clone MaxText
    git clone https://github.com/AI-Hypercomputer/maxtext.git
    cd maxtext
    git checkout maxtext-tutorial-v1.0.0
    ```

    ```shell
    # Custom Jax and LibTPU wheels
    pip download libtpu==0.0.28.dev20251104+nightly -f "https://storage.googleapis.com/jax-releases/libtpu_releases.html"
    pip download --pre jax==0.8.1.dev20251104 jaxlib==0.8.1.dev20251104 --index https://us-python.pkg.dev/ml-oss-artifacts-published/jax/simple/
    ```

    ```shell
    # Build the Docker image
    bash docker_build_dependency_image.sh MODE=custom_wheels
    ```

    After the successful execution of the commands, you should see an image named
    `maxtext_base_image` created locally. You can use your local image directly in
    the xpk workload command.

1. Run a MaxText workload on the cluster.

    ```shell
    export MAXTEXT_COMMAND="JAX_PLATFORMS=tpu,cpu \
      ENABLE_PJRT_COMPATIBILITY=true \
      python3 src/MaxText/train.py src/MaxText/configs/base.yml \
          base_output_directory=$BASE_OUTPUT_DIR \
          dataset_type=synthetic \
          per_device_batch_size=2 \
          enable_checkpointing=false \
          run_name=maxtext_xpk \
          steps=30"

    xpk workload create \
        --cluster ${CLUSTER_NAME} \
        --base-docker-image maxtext_base_image \
        --workload maxtext-1b-$(date +%H%M) \
        --tpu-type=${ACCELERATOR_TYPE} \
        --zone ${ZONE} \
        --project ${PROJECT_ID} \
        --command "${MAXTEXT_COMMAND}"
    ```

</details>
