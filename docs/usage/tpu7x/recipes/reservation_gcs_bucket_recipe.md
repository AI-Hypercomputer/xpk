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

# Run training workload with Ironwood and regular/gSC/DWS Calendar reservations using GCS Bucket storage

## Create a cluster with regular/gSC/DWS Calendar reservation

Use the following instructions if you have access to regular reservations or gSupercomputer (gSC) reservation or DWS Calendar reservation.

### Before you begin

Before you start, complete the following steps:

* Make sure that you have XPK and its prerequisites installed by following instructions found [here](/docs/installation.md).
* Ensure you have a Google Cloud project with billing enabled.
* Get access to TPU7x. For more information, contact your account team.
* Ensure the account you're using with XPK has the roles listed in the [XPK GitHub repository](https://github.com/AI-Hypercomputer/xpk/blob/main/docs/permissions.md).

### Create a single-NIC, single slice cluster

1. Set the following environment variables:

    > **NOTE:** For multi-host provisioning use an ACCELERATOR_TYPE with any topology that results to more than 8 chips, e.g. `tpu7x-2x2x2` or `tpu7x-16`. For single-host provisioning use an ACCELERATOR_TYPE with any topology that results to 8 or less chips, e.g. `tpu7x-2x2x1` or `tpu7x-8`.

    > **NOTE:** The reservation can be of any type e.g. DWS Calendar reservation, gSC reservation or non-gSC reservation.

    ```shell
    export PROJECT_ID=<project_id> # Your GCP project name
    export ZONE=<zone> # Example: us-central1-c
    export CLUSTER_NAME=<cluster_name> # Your cluster name
    # For a list of supported topologies, see: https://docs.cloud.google.com/tpu/docs/tpu/docs/tpu7x#configurations
    export ACCELERATOR_TYPE=<tpu_type> # Example:tpu7x-2x2x2
    export RESERVATION_NAME=<reservation_name> # Your TPU reservation name if within the same project. For shared project use "projects/<project_number>/reservations/<reservation_name>"
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
        --reservation=${RESERVATION_NAME} \
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
<summary><strong>Option B: Training a generic model with MaxText</strong></summary>

1. Create a GCS bucket by running the commands below:

    ```shell
    export BASE_OUTPUT_DIR="gs://<your_gcs_bucket>" # Output directory for model training
    gcloud storage buckets create ${BASE_OUTPUT_DIR} --project=${PROJECT_ID} --location=US \
        --default-storage-class=STANDARD --uniform-bucket-level-access
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
    pip install flax==0.12.0
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
          gcs_metrics=true \
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

<details>
<summary><strong>Option C: Training a Llama3.1 model with MaxText</strong></summary>

 > **NOTE:** For Llama3.1-70b it is recommended that you use at least a 4x4x4 topology (i.e. 64 chips). If the cluster you created uses less chips, recreate the cluster with a larger topology before running the steps below.

1. Create a GCS bucket by running the commands below:

    ```shell
    export BASE_OUTPUT_DIR="gs://<your_gcs_bucket>" # Output directory for model training
    gcloud storage buckets create ${BASE_OUTPUT_DIR} --project=${PROJECT_ID} --location=US \
        --default-storage-class=STANDARD --uniform-bucket-level-access
    ```

1. Build the Docker Image

    ```shell
    export CONTAINER_REGISTRY=<registry_name> # Initialize with your registry e.g. gcr.io
    export CLOUD_IMAGE_NAME="llama-maxtext-runner"
    export WORKLOAD_IMAGE="${CONTAINER_REGISTRY}/${PROJECT_ID}/${CLOUD_IMAGE_NAME}"
    ```

    ```shell
    # Make sure you're running on a Virtual Environment with python 3.12
    if [[ "$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null)" == "3.12" ]]; then { echo You have the correct Python version 3.12; } else { >&2 echo Error: Python version must be 3.12; } fi
    ```

    ```shell
    # Clone MaxText Repository and Checkout Recipe Branch
    git clone https://github.com/AI-Hypercomputer/maxtext.git
    cd maxtext
    git checkout maxtext-tutorial-v1.3.0
    ```

    ```shell
    # Custom Jax and LibTPU wheels
    pip download libtpu==0.0.31.dev20251119+nightly -f"https://storage.googleapis.com/jax-releases/libtpu_releases.html"
    pip download --pre jax==0.8.1 jaxlib==0.8.1 --index https://us-python.pkg.dev/ml-oss-artifacts-published/jax/simple/
    ```

    ```shell
    # Build and upload the docker image
    bash dependencies/scripts/docker_build_dependency_image.sh MODE=custom_wheels
    bash dependencies/scripts/docker_upload_runner.sh CLOUD_IMAGE_NAME=${CLOUD_IMAGE_NAME}
    ```

1. Run the Llama 3.1 MaxText workload on the cluster.

    ```shell
    export WORKLOAD_NAME="$(printf "%.26s" "llama3-1-70b-8192-fp8-4x4x4")-$(date +%Y%m%d-%H%M)"
    export XLA_FLAGS=" \
      --xla_tpu_scoped_vmem_limit_kib=65536 \
      --xla_tpu_bf16_emission_mode=NATIVE_EMISSION \
      --xla_tpu_enable_sparse_core_reduce_scatter_v2=true \
      --xla_tpu_enable_sparse_core_collective_offload_all_gather=true \
      --xla_tpu_enable_sparse_core_collective_offload_2d_all_gather=true \
      --xla_tpu_enable_all_gather_offload_tracing=true \
      --xla_tpu_use_tc_device_shape_on_sc=True \
      --xla_sc_disable_megacore_partitioning=True \
      --xla_tpu_enable_async_collective_fusion_fuse_all_gather=false \
      --xla_enable_async_all_gather=true \
      --xla_tpu_prefer_async_allgather_to_allreduce=true \
      --xla_tpu_enable_sparse_core_collective_offload_all_reduce=true \
      --xla_tpu_enable_sparse_core_collective_offload_reduce_scatter=true \
      --xla_tpu_enable_sparse_core_collective_offload_3d_all_gather=true \
      --xla_tpu_use_single_sparse_core_for_all_gather_offload=true "

    export MAXTEXT_ARGS="\
      model_name=llama3.1-70b \
      skip_jax_distributed_system=True \
      dtype=bfloat16 \
      per_device_batch_size=2 \
      profile_periodically_period=10000 \
      async_checkpointing=False \
      enable_checkpointing=False \
      use_iota_embed=True \
      remat_policy=custom \
      decoder_layer_input=device \
      context=device \
      query_proj=device \
      key_proj=device \
      value_proj=device \
      ici_fsdp_parallelism=-1 \
      dataset_type=synthetic \
      opt_type=adamw \
      mu_dtype=bfloat16 \
      sa_block_q=2048 \
      sa_block_kv=1024 \
      sa_block_kv_compute=512 \
      sa_block_q_dkv=2048 \
      sa_block_kv_dkv=2048 \
      sa_block_kv_dkv_compute=256 \
      sa_q_layout=SEQ_MINOR \
      sa_k_layout=SEQ_MINOR \
      sa_v_layout=HEAD_DIM_MINOR \
      sa_use_fused_bwd_kernel=True \
      use_tokamax_splash=True \
      max_target_length=8192 \
      profiler=xplane \
      skip_first_n_steps_for_profiler=5 \
      profiler_steps=2 \
      attention=flash \
      quantization=fp8_full \
      use_qwix_quantization=True \
      steps=30 \
      base_output_directory=${BASE_OUTPUT_DIR} \
      run_name=${WORKLOAD_NAME}"

    xpk workload create \
      --cluster=${CLUSTER_NAME} \
      --project=${PROJECT_ID} \
      --zone=${ZONE} \
      --priority=very-high \
      --max-restarts=0 \
      --device-type=${ACCELERATOR_TYPE} \
      --num-slices=1 \
      --docker-image="${WORKLOAD_IMAGE}" \
      --enable-debug-logs \
      --workload="${WORKLOAD_NAME}" \
      --command="set -e && export ENABLE_PATHWAYS_PERSISTENCE='1' && \
    export LIBTPU_INIT_ARGS='${XLA_FLAGS}' && \
    export JAX_PLATFORMS='tpu,cpu' && export ENABLE_PJRT_COMPATIBILITY='true' && \
    python3 -m MaxText.train MaxText/configs/base.yml ${MAXTEXT_ARGS}"

</details>
