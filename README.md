<!--
 Copyright 2023 Google LLC

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

[![Build Tests](https://github.com/google/xpk/actions/workflows/build_tests.yaml/badge.svg)](https://github.com/google/xpk/actions/workflows/build_tests.yaml)
[![Nightly Tests](https://github.com/google/xpk/actions/workflows/nightly_tests.yaml/badge.svg)](https://github.com/google/xpk/actions/workflows/nightly_tests.yaml)
[![Develop Tests](https://github.com/AI-Hypercomputer/xpk/actions/workflows/build_tests.yaml/badge.svg?branch=develop)](https://github.com/AI-Hypercomputer/xpk/actions/workflows/build_tests.yaml)
[![Develop Nightly Tests](https://github.com/AI-Hypercomputer/xpk/actions/workflows/nightly_tests.yaml/badge.svg?branch=develop)](https://github.com/AI-Hypercomputer/xpk/actions/workflows/nightly_tests.yaml)

# Overview

xpk (Accelerated Processing Kit, pronounced x-p-k,) is a software tool to help
Cloud developers to orchestrate training jobs on accelerators such as TPUs and
GPUs on GKE. xpk handles the "multihost pods" of TPUs, GPUs (HGX H100) and CPUs
(n2-standard-32) as first class citizens.

xpk decouples provisioning capacity from running jobs. There are two structures:
clusters (provisioned VMs) and workloads (training jobs). Clusters represent the
physical resources you have available. Workloads represent training jobs -- at
any time some of these will be completed, others will be running and some will
be queued, waiting for cluster resources to become available.

The ideal workflow starts by provisioning the clusters for all of the ML
hardware you have reserved. Then, without re-provisioning, submit jobs as
needed. By eliminating the need for re-provisioning between jobs, using Docker
containers with pre-installed dependencies and cross-ahead of time compilation,
these queued jobs run with minimal start times. Further, because workloads
return the hardware back to the shared pool when they complete, developers can
achieve better use of finite hardware resources. And automated tests can run
overnight while resources tend to be underutilized.

xpk supports the following TPU types:
* v4
* v5e
* v5p
* Trillium (v6e)

and the following GPU types:
* A100
* A3-Highgpu (h100)
* A3-Mega (h100-mega) - [Create cluster](#provisioning-a3-ultra-and-a3-mega-clusters-gpu-machines), [Create workloads](#workloads-for-a3-ultra-and-a3-mega-clusters-gpu-machines)
* A3-Ultra (h200) - [Create cluster](#provisioning-a3-ultra-and-a3-mega-clusters-gpu-machines), [Create workloads](#workloads-for-a3-ultra-and-a3-mega-clusters-gpu-machines)

and the following CPU types:
* n2-standard-32

xpk also supports Google Cloud Storage solutions:
* [Cloud Storage FUSE](#fuse)
* [Filestore](#filestore)

# Permissions needed on Cloud Console:

* Artifact Registry Writer
* Compute Admin
* Kubernetes Engine Admin
* Logging Admin
* Monitoring Admin
* Service Account User
* Storage Admin
* Vertex AI Administrator
* Filestore Editor (This role is neccessary if you want to run `storage create` command with `--type=gcpfilestore`)

# Prerequisites

Following tools must be installed:

- python >= 3.10 (download from [here](https://www.python.org/downloads/))
- pip ([installation instruction](https://pip.pypa.io/en/stable/installation/))
- python venv ([installation instruction](https://virtualenv.pypa.io/en/latest/installation.html))
(all three of above can be installed at once from [here](https://packaging.python.org/en/latest/guides/installing-using-linux-tools/#installing-pip-setuptools-wheel-with-linux-package-managers))
- gcloud (install from [here](https://cloud.google.com/sdk/gcloud#download_and_install_the))
  - Run `gcloud init` 
  - [Authenticate](https://cloud.google.com/sdk/gcloud/reference/auth/application-default/login) to Google Cloud
- kubectl (install from [here](https://cloud.google.com/kubernetes-engine/docs/how-to/cluster-access-for-kubectl#install_kubectl))
  - Install `gke-gcloud-auth-plugin` from [here](https://cloud.google.com/kubernetes-engine/docs/how-to/cluster-access-for-kubectl#install_plugin)
- docker ([installation instruction](https://docs.docker.com/engine/install/))
  - Run `gcloud auth configure-docker` to ensure images can be uploaded to registry 
- make - please run below command.
```shell
# sudo may be required
apt-get -y install make
```
In addition, below dependencies can be installed either using provided links or using `make install` command, if xpk is downloaded via `git clone` command:
- kueuectl (install from [here](https://kueue.sigs.k8s.io/docs/reference/kubectl-kueue/installation/))
- kjob (installation instructions [here](https://github.com/kubernetes-sigs/kjob/blob/main/docs/installation.md))

# Installation
To install xpk, install required tools mentioned in [prerequisites](#prerequisites). [Makefile](https://github.com/AI-Hypercomputer/xpk/blob/main/Makefile) provides a way to install all neccessary tools. XPK can be installed via pip:

```shell
pip install xpk
```

If you see an error saying: `This environment is externally managed`, please use a virtual environment.

```shell
  ## One time step of creating the venv
  VENV_DIR=~/venvp3
  python3 -m venv $VENV_DIR
  ## Enter your venv.
  source $VENV_DIR/bin/activate
  ## Clone the repository and installing dependencies.
  pip install xpk
```

If you are running XPK by cloning GitHub repository, first run the
following commands to begin using XPK commands:

```shell
git clone https://github.com/google/xpk.git
cd xpk
# Install required dependencies with make
make install && export PATH=$PATH:$PWD/bin
```

If you want to have installed dependecies persist in your PATH please run:
`echo $PWD/bin` and add its value to `PATH` in .bashrc  or .zshrc

If you see an error saying: `This environment is externally managed`, please use a virtual environment.

Example:

```shell
  ## One time step of creating the venv
  VENV_DIR=~/venvp3
  python3 -m venv $VENV_DIR
  ## Enter your venv.
  source $VENV_DIR/bin/activate
  ## Clone the repository and installing dependencies.
  git clone https://github.com/google/xpk.git
  cd xpk
  # Install required dependencies with make
  make install && export PATH=$PATH:$PWD/bin
```

# XPK for Large Scale (>1k VMs)

Follow user instructions in [xpk-large-scale-guide.sh](xpk-large-scale-guide.sh)
to use xpk for a GKE cluster greater than 1000 VMs. Run these steps to set up a
GKE cluster with large scale training and high throughput support with XPK, and
run jobs with XPK. We recommend you manually copy commands per step and verify
the outputs of each step.

# Example usages:

To get started, be sure to set your GCP Project and Zone as usual via `gcloud
config set`.

Below are reference commands. A typical journey starts with a `Cluster Create`
followed by many `Workload Create`s. To understand the state of the system you
might want to use `Cluster List` or `Workload List` commands. Finally, you can
cleanup with a `Cluster Delete`.

If you have failures with workloads not running, use `xpk inspector` to investigate
more.

If you need your Workloads to have persistent storage, use `xpk storage` to find out more.

## Cluster Create

First set the project and zone through gcloud config or xpk arguments.

```shell
PROJECT_ID=my-project-id
ZONE=us-east5-b
# gcloud config:
gcloud config set project $PROJECT_ID
gcloud config set compute/zone $ZONE
# xpk arguments
xpk .. --zone $ZONE --project $PROJECT_ID
```

The cluster created is a regional cluster to enable the GKE control plane across
all zones.

*   Cluster Create (provision reserved capacity):

    ```shell
    # Find your reservations
    gcloud compute reservations list --project=$PROJECT_ID
    # Run cluster create with reservation.
    python3 xpk.py cluster create \
    --cluster xpk-test --tpu-type=v5litepod-256 \
    --num-slices=2 \
    --reservation=$RESERVATION_ID
    ```

*   Cluster Create (provision on-demand capacity):

    ```shell
    python3 xpk.py cluster create \
    --cluster xpk-test --tpu-type=v5litepod-16 \
    --num-slices=4 --on-demand
    ```

*   Cluster Create (provision spot / preemptable capacity):

    ```shell
    python3 xpk.py cluster create \
    --cluster xpk-test --tpu-type=v5litepod-16 \
    --num-slices=4 --spot
    ```

* Cluster Create for Pathways:
    Pathways compatible cluster can be created using `cluster create-pathways`.
    ```shell
    python3 xpk.py cluster create-pathways \
    --cluster xpk-pw-test \
    --num-slices=4 --on-demand \
    --tpu-type=v5litepod-16
    ```

*   Cluster Create for Ray:
    A cluster with KubeRay enabled and a RayCluster can be created using `cluster create-ray`.
    ```shell
    python3 xpk.py cluster create-ray \
    --cluster xpk-rc-test \
    --ray-version=2.39.0 \
    --num-slices=4 --on-demand \
    --tpu-type=v5litepod-8
    ```

*   Cluster Create can be called again with the same `--cluster name` to modify
    the number of slices or retry failed steps.

    For example, if a user creates a cluster with 4 slices:

    ```shell
    python3 xpk.py cluster create \
    --cluster xpk-test --tpu-type=v5litepod-16 \
    --num-slices=4  --reservation=$RESERVATION_ID
    ```

    and recreates the cluster with 8 slices. The command will rerun to create 4
    new slices:

    ```shell
    python3 xpk.py cluster create \
    --cluster xpk-test --tpu-type=v5litepod-16 \
    --num-slices=8  --reservation=$RESERVATION_ID
    ```

    and recreates the cluster with 6 slices. The command will rerun to delete 2
    slices. The command will warn the user when deleting slices.
    Use `--force` to skip prompts.

    ```shell
    python3 xpk.py cluster create \
    --cluster xpk-test --tpu-type=v5litepod-16 \
    --num-slices=6  --reservation=$RESERVATION_ID

    # Skip delete prompts using --force.

    python3 xpk.py cluster create --force \
    --cluster xpk-test --tpu-type=v5litepod-16 \
    --num-slices=6  --reservation=$RESERVATION_ID
    ```

    and recreates the cluster with 4 slices of v4-8. The command will rerun to delete
    6 slices of v5litepod-16 and create 4 slices of v4-8. The command will warn the
    user when deleting slices. Use `--force` to skip prompts.

    ```shell
    python3 xpk.py cluster create \
    --cluster xpk-test --tpu-type=v4-8 \
    --num-slices=4  --reservation=$RESERVATION_ID

    # Skip delete prompts using --force.

    python3 xpk.py cluster create --force \
    --cluster xpk-test --tpu-type=v4-8 \
    --num-slices=4  --reservation=$RESERVATION_ID
    ```

### Create Private Cluster

XPK allows you to create a private GKE cluster for enhanced security. In a private cluster, nodes and pods are isolated from the public internet, providing an additional layer of protection for your workloads.

To create a private cluster, use the following arguments:

**`--private`**

This flag enables the creation of a private GKE cluster. When this flag is set:

*  Nodes and pods are isolated from the direct internet access.
*  `master_authorized_networks` is automatically enabled.
*  Access to the cluster's control plane is restricted to your current machine's IP address by default.

**`--authorized-networks`**

This argument allows you to specify additional IP ranges (in CIDR notation) that are authorized to access the private cluster's control plane and perform `kubectl` commands. 

*  Even if this argument is not set when you have `--private`, your current machine's IP address will always be given access to the control plane.
*  If this argument is used with an existing private cluster, it will replace the existing authorized networks.

**Example Usage:**

* To create a private cluster and allow access to Control Plane only to your current machine:

  ```shell
  python3 xpk.py cluster create \
    --cluster=xpk-private-cluster \
    --tpu-type=v4-8 --num-slices=2 \
    --private
  ```

* To create a private cluster and allow access to Control Plane only to your current machine and the IP ranges `1.2.3.0/24` and `1.2.4.5/32`:

  ```shell
  python3 xpk.py cluster create \
    --cluster=xpk-private-cluster \
    --tpu-type=v4-8 --num-slices=2 \
    --authorized-networks 1.2.3.0/24 1.2.4.5/32

    # --private is optional when you set --authorized-networks
  ```

> **Important Notes:** 
> * The argument `--private` is only applicable when creating new clusters. You cannot convert an existing public cluster to a private cluster using these flags.
> * The argument `--authorized-networks` is applicable when creating new clusters or using an existing _*private*_ cluster. You cannot convert an existing public cluster to a private cluster using these flags.
> * You need to [set up a Cluster NAT for your VPC network](https://cloud.google.com/nat/docs/set-up-manage-network-address-translation#creating_nat) so that the Nodes and Pods have outbound access to the internet. This is required because XPK installs and configures components such as kueue that need access to external sources like `registry.k8.io`.


### Create Vertex AI Tensorboard
*Note: This feature is available in XPK >= 0.4.0. Enable [Vertex AI API](https://cloud.google.com/vertex-ai/docs/start/cloud-environment#enable_vertexai_apis) in your Google Cloud console to use this feature. Make sure you have
[Vertex AI Administrator](https://cloud.google.com/vertex-ai/docs/general/access-control#aiplatform.admin) role
assigned to your user account.*

Vertex AI Tensorboard is a fully managed version of open-source Tensorboard. To learn more about Vertex AI Tensorboard, visit [this](https://cloud.google.com/vertex-ai/docs/experiments/tensorboard-introduction). Note that Vertex AI Tensorboard is only available in [these](https://cloud.google.com/vertex-ai/docs/general/locations#available-regions) regions.

You can create a Vertex AI Tensorboard for your cluster with `Cluster Create` command. XPK will create a single Vertex AI Tensorboard instance per cluster.

* Create Vertex AI Tensorboard in default region with default Tensorboard name:

```shell
python3 xpk.py cluster create \
--cluster xpk-test --num-slices=1 --tpu-type=v4-8 \
--create-vertex-tensorboard
```

will create a Vertex AI Tensorboard with the name `xpk-test-tb-instance` (*<args.cluster>-tb-instance*) in `us-central1` (*default region*).

* Create Vertex AI Tensorboard in user-specified region with default Tensorboard name:

```shell
python3 xpk.py cluster create \
--cluster xpk-test --num-slices=1 --tpu-type=v4-8 \
--create-vertex-tensorboard --tensorboard-region=us-west1
```

will create a Vertex AI Tensorboard with the name `xpk-test-tb-instance` (*<args.cluster>-tb-instance*) in `us-west1`.

* Create Vertex AI Tensorboard in default region with user-specified Tensorboard name:

```shell
python3 xpk.py cluster create \
--cluster xpk-test --num-slices=1 --tpu-type=v4-8 \
--create-vertex-tensorboard --tensorboard-name=tb-testing
```

will create a Vertex AI Tensorboard with the name `tb-testing` in `us-central1`.

* Create Vertex AI Tensorboard in user-specified region with user-specified Tensorboard name:

```shell
python3 xpk.py cluster create \
--cluster xpk-test --num-slices=1 --tpu-type=v4-8 \
--create-vertex-tensorboard --tensorboard-region=us-west1 --tensorboard-name=tb-testing
```

will create a Vertex AI Tensorboard instance with the name `tb-testing` in `us-west1`.

* Create Vertex AI Tensorboard in an unsupported region:

```shell
python3 xpk.py cluster create \
--cluster xpk-test --num-slices=1 --tpu-type=v4-8 \
--create-vertex-tensorboard --tensorboard-region=us-central2
```

will fail the cluster creation process because Vertex AI Tensorboard is not supported in `us-central2`.

## Cluster Delete
*   Cluster Delete (deprovision capacity):

    ```shell
    python3 xpk.py cluster delete \
    --cluster xpk-test
    ```
## Cluster List
*   Cluster List (see provisioned capacity):

    ```shell
    python3 xpk.py cluster list
    ```
## Cluster Describe
*   Cluster Describe (see capacity):

    ```shell
    python3 xpk.py cluster describe \
    --cluster xpk-test
    ```

## Cluster Cacheimage
*   Cluster Cacheimage (enables faster start times):

    ```shell
    python3 xpk.py cluster cacheimage \
    --cluster xpk-test --docker-image gcr.io/your_docker_image \
    --tpu-type=v5litepod-16
    ```

## Provisioning A3-Ultra and A3-Mega clusters (GPU machines)
To create a cluster with A3 machines, run the below command. To create workloads on these clusters see [here](#workloads-for-a3-ultra-and-a3-mega-clusters-gpu-machines).
  * For A3-Ultra: --device-type=h200-141gb-8
  * For A3-Mega: --device-type=h100-mega-80gb-8

  ```shell
  python3 xpk.py cluster create \
  --cluster CLUSTER_NAME --device-type=h200-141gb-8 \
  --zone=$COMPUTE_ZONE  --project=$PROJECT_ID \
  --num-nodes=4 --reservation=$RESERVATION_ID
  ```
Currently, the below flags/arguments are supported for A3-Mega and A3-Ultra machines:
  * --num-nodes
  * --default-pool-cpu-machine-type
  * --default-pool-cpu-num-nodes
  * --reservation
  * --spot
  * --on-demand (only A3-Mega)


## Storage
Currently XPK supports two types of storages: Cloud Storage FUSE and Google Cloud Filestore.

### FUSE
A FUSE adapter lets you mount and access Cloud Storage buckets as local file systems, so applications can read and write objects in your bucket using standard file system semantics.

To use the GCS FUSE with XPK you need to create a [Storage Bucket](https://console.cloud.google.com/storage/).

Once it's ready you can use `xpk storage attach` with `--type=gcsfuse` command to attach a FUSE storage instance to your cluster:

```shell
python3 xpk.py storage attach test-fuse-storage --type=gcsfuse \
  --project=$PROJECT --cluster=$CLUSTER --zone=$ZONE 
  --mount-point='/test-mount-point' --readonly=false \
  --bucket=test-bucket --size=1 --auto-mount=false
```

Parameters:

- `--type` - type of the storage, currently xpk supports `gcsfuse` and `gcpfilestore` only.
- `--auto-mount` - if set to true all workloads will have this storage mounted by default.
- `--mount-point` - the path on which this storage should be mounted for a workload.
- `--readonly` - if set to true, workload can only read from storage.
- `--size` - size of the storage in Gb.
- `--bucket` - name of the storage bucket. If not set then the name of the storage is used as a bucket name.
- `--manifest` - path to the manifest file containing PersistentVolume and PresistentVolumeClaim definitions. If set, then values from manifest override the following parameters: `--size` and `--bucket`.

### Filestore

A Filestore adapter lets you mount and access [Filestore instances](https://cloud.google.com/filestore/) as local file systems, so applications can read and write objects in your volumes using standard file system semantics.

To create and attach a GCP Filestore instance to your cluster use `xpk storage create` command with `--type=gcpfilestore`:

```shell
python3 xpk.py storage create test-fs-storage --type=gcpfilestore \
  --auto-mount=false --mount-point=/data-fs --readonly=false \
  --size=1024 --tier=BASIC_HDD --access_mode=ReadWriteMany --vol=default \
  --project=$PROJECT --cluster=$CLUSTER --zone=$ZONE
```

You can also attach an existing Filestore instance to your cluster using `xpk storage attach` command:

```shell
python3 xpk.py storage attach test-fs-storage --type=gcpfilestore \
  --auto-mount=false --mount-point=/data-fs --readonly=false \
  --size=1024 --tier=BASIC_HDD --access_mode=ReadWriteMany --vol=default \
  --project=$PROJECT --cluster=$CLUSTER --zone=$ZONE
```

The command above is also useful when attaching multiple volumes from the same Filestore instance.

Commands `xpk storage create` and `xpk storage attach` with `--type=gcpfilestore` accept following arguments:
- `--type` - type of the storage.
- `--auto-mount` - if set to true all workloads will have this storage mounted by default.
- `--mount-point` - the path on which this storage should be mounted for a workload.
- `--readonly` - if set to true, workload can only read from storage.
- `--size` - size of the Filestore instance that will be created in Gb.
- `--tier` - tier of the Filestore instance that will be created. Possible options are: `[BASIC_HDD, BASIC_SSD, ZONAL, REGIONAL, ENTERPRISE]`
- `--access-mode` - access mode of the Filestore instance that will be created. Possible values are: `[ReadWriteOnce, ReadOnlyMany, ReadWriteMany]`
- `--vol` - file share name of the Filestore instance that will be created.
- `--instance` - the name of the Filestore instance. If not set then the name parameter is used as an instance name. Useful when connecting multiple volumes from the same Filestore instance.
- `--manifest` - path to the manifest file containing PersistentVolume, PresistentVolumeClaim and StorageClass definitions. If set, then values from manifest override the following parameters: `--access-mode`, `--size` and `--volume`.

### List attached storages

```shell
python3 xpk.py storage list \
  --project=$PROJECT --cluster $CLUSTER --zone=$ZONE
```

### Running workloads with storage

If you specified `--auto-mount=true` when creating or attaching a storage, then all workloads deployed on the cluster will have the volume attached by default. Otherwise, in order to have the storage attached, you have to add `--storage` parameter to `workload create` command:

```shell
python3 xpk.py workload create \
  --workload xpk-test-workload --command "echo goodbye" \
  --project=$PROJECT --cluster=$CLUSTER --zone=$ZONE \
  --tpu-type=v5litepod-16 --storage=test-storage
```

### Detaching storage

```shell
python3 xpk.py storage detach $STORAGE_NAME \
  --project=$PROJECT --cluster=$CLUSTER --zone=$ZONE
```

### Deleting storage

XPK allows you to remove Filestore instances easily with `xpk storage delete` command. **Warning:** this deletes all data contained in the Filestore!

```shell
python3 xpk.py storage delete test-fs-instance \
  --project=$PROJECT --cluster=$CLUSTER --zone=$ZONE
```

## Workload Create
*   Workload Create (submit training job):

    ```shell
    python3 xpk.py workload create \
    --workload xpk-test-workload --command "echo goodbye" \
    --cluster xpk-test \
    --tpu-type=v5litepod-16 --projet=$PROJECT
    ```

*   Workload Create for Pathways:
    Pathways workload can be submitted using `workload create-pathways` on a Pathways enabled cluster (created with `cluster create-pathways`)

    Pathways workload example:
    ```shell
    python3 xpk.py workload create-pathways \
    --workload xpk-pw-test \
    --num-slices=1 \
    --tpu-type=v5litepod-16 \
    --cluster xpk-pw-test \
    --docker-name='user-workload' \
    --docker-image=<maxtext docker image> \
    --command='python3 MaxText/train.py MaxText/configs/base.yml base_output_directory=<output directory> dataset_path=<dataset path> per_device_batch_size=1 enable_checkpointing=false enable_profiler=false remat_policy=full global_parameter_scale=4 steps=300 max_target_length=2048 use_iota_embed=true reuse_example_batch=1 dataset_type=synthetic attention=flash gcs_metrics=True run_name=$(USER)-pw-xpk-test-1'
    ```

    Regular workload can also be submitted on a Pathways enabled cluster (created with `cluster create-pathways`)

    Pathways workload example:
    ```shell
    python3 xpk.py workload create-pathways \
    --workload xpk-regular-test \
    --num-slices=1 \
    --tpu-type=v5litepod-16 \
    --cluster xpk-pw-test \
    --docker-name='user-workload' \
    --docker-image=<maxtext docker image> \
    --command='python3 MaxText/train.py MaxText/configs/base.yml base_output_directory=<output directory> dataset_path=<dataset path> per_device_batch_size=1 enable_checkpointing=false enable_profiler=false remat_policy=full global_parameter_scale=4 steps=300 max_target_length=2048 use_iota_embed=true reuse_example_batch=1 dataset_type=synthetic attention=flash gcs_metrics=True run_name=$(USER)-pw-xpk-test-1'
    ```

    Pathways in headless mode - Pathways now offers the capability to run JAX workloads in Vertex AI notebooks or in GCE VMs!
    Specify `--headless` with `workload create-pathways` when the user workload is not provided in a docker container.
    ```shell
    python3 xpk.py workload create-pathways --headless \
    --workload xpk-pw-headless \
    --num-slices=1 \
    --tpu-type=v5litepod-16 \
    --cluster xpk-pw-test
    ```
    Executing the command above would provide the address of the proxy that the user job should connect to.
    ```shell
    kubectl get pods
    kubectl port-forward pod/<proxy-pod-name> 29000:29000
    ```
    ```shell
    JAX_PLATFORMS=proxy JAX_BACKEND_TARGET=grpc://127.0.0.1:29000 python -c 'import pathwaysutils; import jax; print(jax.devices())'
    ```
    Specify `JAX_PLATFORMS=proxy` and `JAX_BACKEND_TARGET=<proxy address from above>` and `import pathwaysutils` to establish this connection between the user's JAX code and the Pathways proxy. Execute Pathways workloads interactively on Vertex AI notebooks!

### Set `max-restarts` for production jobs

* `--max-restarts <value>`: By default, this is 0. This will restart the job ""
times when the job terminates. For production jobs, it is recommended to
increase this to a large number, say 50. Real jobs can be interrupted due to
hardware failures and software updates. We assume your job has implemented
checkpointing so the job restarts near where it was interrupted.

### Workloads for A3-Ultra and A3-Mega clusters (GPU machines)
To submit jobs on a cluster with A3 machines, run the below command. To create a cluster with A3 machines see [here](#provisioning-a3-ultra-and-a3-mega-clusters-gpu-machines).
  * For A3-Ultra: --device-type=h200-141gb-8
  * For A3-Mega: --device-type=h100-mega-80gb-8

  ```shell
  python3 xpk.py workload create \
  --workload=$WORKLOAD_NAME --command="echo goodbye" \
  --cluster=$CLUSTER_NAME --device-type=h200-141gb-8 \
  --zone=$COMPUTE_ZONE  --project=$PROJECT_ID \
  --num-nodes=$WOKRKLOAD_NUM_NODES
  ```
> The docker image flags/arguments introduced in [workloads section](#workload-create) can be used with A3 machines as well.

In order to run NCCL test on A3 Ultra machines check out [this guide](/examples/nccl/nccl.md).

### Workload Priority and Preemption
* Set the priority level of your workload with `--priority=LEVEL`

  We have five priorities defined: [`very-low`, `low`, `medium`, `high`, `very-high`].
  The default priority is `medium`.

  Priority determines:

  1. Order of queued jobs.

      Queued jobs are ordered by
      `very-low` < `low` < `medium` < `high` <  `very-high`

  2. Preemption of lower priority workloads.

      A higher priority job will `evict` lower priority jobs.
      Evicted jobs are brought back to the queue and will re-hydrate appropriately.

  #### General Example:
  ```shell
  python3 xpk.py workload create \
  --workload xpk-test-medium-workload --command "echo goodbye" --cluster \
  xpk-test --tpu-type=v5litepod-16 --priority=medium
  ```

### Create Vertex AI Experiment to upload data to Vertex AI Tensorboard
*Note: This feature is available in XPK >= 0.4.0. Enable [Vertex AI API](https://cloud.google.com/vertex-ai/docs/start/cloud-environment#enable_vertexai_apis) in your Google Cloud console to use this feature. Make sure you have
[Vertex AI Administrator](https://cloud.google.com/vertex-ai/docs/general/access-control#aiplatform.admin) role
assigned to your user account and to the [Compute Engine Service account](https://cloud.google.com/compute/docs/access/service-accounts#default_service_account) attached to the node pools in the cluster.*

Vertex AI Experiment is a tool that helps to track and analyze an experiment run on Vertex AI Tensorboard. To learn more about Vertex AI Experiments, visit [this](https://cloud.google.com/vertex-ai/docs/experiments/intro-vertex-ai-experiments).

XPK will create a Vertex AI Experiment in `workload create` command and attach the Vertex AI Tensorboard created for the cluster during `cluster create`. If there is a cluster created before this feature is released, there will be no Vertex AI Tensorboard created for the cluster and `workload create` will fail. Re-run `cluster create` to create a Vertex AI Tensorboard and then run `workload create` again to schedule your workload.

* Create Vertex AI Experiment with default Experiment name:

```shell
python3 xpk.py workload create \
--cluster xpk-test --workload xpk-workload \
--use-vertex-tensorboard
```

will create a Vertex AI Experiment with the name `xpk-test-xpk-workload` (*<args.cluster>-<args.workload>*).

* Create Vertex AI Experiment with user-specified Experiment name:

```shell
python3 xpk.py workload create \
--cluster xpk-test --workload xpk-workload \
--use-vertex-tensorboard --experiment-name=test-experiment
```

will create a Vertex AI Experiment with the name `test-experiment`.

Check out [MaxText example](https://github.com/google/maxtext/pull/570) on how to update your workload to automatically upload logs collected in your Tensorboard directory to the Vertex AI Experiment created by `workload create`.

## Workload Delete
*   Workload Delete (delete training job):

    ```shell
    python3 xpk.py workload delete \
    --workload xpk-test-workload --cluster xpk-test
    ```

    This will only delete `xpk-test-workload` workload in `xpk-test` cluster.

*   Workload Delete (delete all training jobs in the cluster):

    ```shell
    python3 xpk.py workload delete \
    --cluster xpk-test
    ```

    This will delete all the workloads in `xpk-test` cluster. Deletion will only begin if you type `y` or `yes` at the prompt. Multiple workload deletions are processed in batches for optimized processing.

*   Workload Delete supports filtering. Delete a portion of jobs that match user criteria. Multiple workload deletions are processed in batches for optimized processing.
    * Filter by Job: `filter-by-job`

    ```shell
    python3 xpk.py workload delete \
    --cluster xpk-test --filter-by-job=$USER
    ```

    This will delete all the workloads in `xpk-test` cluster whose names start with `$USER`. Deletion will only begin if you type `y` or `yes` at the prompt.

    * Filter by Status: `filter-by-status`

    ```shell
    python3 xpk.py workload delete \
    --cluster xpk-test --filter-by-status=QUEUED
    ```

    This will delete all the workloads in `xpk-test` cluster that have the status as Admitted or Evicted, and the number of running VMs is 0. Deletion will only begin if you type `y` or `yes` at the prompt. Status can be: `EVERYTHING`,`FINISHED`, `RUNNING`, `QUEUED`, `FAILED`, `SUCCESSFUL`.

## Workload List
*   Workload List (see training jobs):

    ```shell
    python3 xpk.py workload list \
    --cluster xpk-test
    ```

* Example Workload List Output:

  The below example shows four jobs of different statuses:

  * `user-first-job-failed`: **filter-status** is `FINISHED` and `FAILED`.
  * `user-second-job-success`: **filter-status** is `FINISHED` and `SUCCESSFUL`.
  * `user-third-job-running`: **filter-status** is `RUNNING`.
  * `user-forth-job-in-queue`: **filter-status** is `QUEUED`.
  * `user-fifth-job-in-queue-preempted`: **filter-status** is `QUEUED`.

  ```
  Jobset Name                     Created Time           Priority   TPU VMs Needed   TPU VMs Running/Ran   TPU VMs Done      Status     Status Message                                                  Status Time
  user-first-job-failed           2023-1-1T1:00:00Z      medium     4                4                     <none>            Finished   JobSet failed                                                   2023-1-1T1:05:00Z
  user-second-job-success         2023-1-1T1:10:00Z      medium     4                4                     4                 Finished   JobSet finished successfully                                    2023-1-1T1:14:00Z
  user-third-job-running          2023-1-1T1:15:00Z      medium     4                4                     <none>            Admitted   Admitted by ClusterQueue cluster-queue                          2023-1-1T1:16:00Z
  user-forth-job-in-queue         2023-1-1T1:16:05Z      medium     4                <none>                <none>            Admitted   couldn't assign flavors to pod set slice-job: insufficient unused quota for google.com/tpu in flavor 2xv4-8, 4 more need   2023-1-1T1:16:10Z
  user-fifth-job-preempted        2023-1-1T1:10:05Z      low        4                <none>                <none>            Evicted    Preempted to accommodate a higher priority Workload             2023-1-1T1:10:00Z
  ```

* Workload List supports filtering. Observe a portion of jobs that match user criteria.

  * Filter by Status: `filter-by-status`

  Filter the workload list by the status of respective jobs.
  Status can be: `EVERYTHING`,`FINISHED`, `RUNNING`, `QUEUED`, `FAILED`, `SUCCESSFUL`

  * Filter by Job: `filter-by-job`

  Filter the workload list by the name of a job.

    ```shell
    python3 xpk.py workload list \
    --cluster xpk-test --filter-by-job=$USER
    ```

* Workload List supports waiting for the completion of a specific job. XPK will follow an existing job until it has finished or the `timeout`, if provided, has been reached  and then list the job. If no `timeout` is specified, the default value is set to the max value, 1 week. You may also set `timeout=0` to poll the job once.

  Wait for a job to complete.

    ```shell
    python3 xpk.py workload list \
    --cluster xpk-test --wait-for-job-completion=xpk-test-workload
    ```

  Wait for a job to complete with a timeout of 300 seconds.

    ```shell
    python3 xpk.py workload list \
    --cluster xpk-test --wait-for-job-completion=xpk-test-workload \
    --timeout=300
    ```

  Return codes
    `0`: Workload finished and completed successfully.
    `124`: Timeout was reached before workload finished.
    `125`: Workload finished but did not complete successfully.
    `1`: Other failure.

## Job List

*   Job List (see jobs submitted via batch command):

    ```shell
    python3 xpk.py job ls --cluster xpk-test
    ```

* Example Job List Output:

  ```
    NAME                              PROFILE               LOCAL QUEUE   COMPLETIONS   DURATION   AGE
    xpk-def-app-profile-slurm-74kbv   xpk-def-app-profile                 1/1           15s        17h
    xpk-def-app-profile-slurm-brcsg   xpk-def-app-profile                 1/1           9s         3h56m
    xpk-def-app-profile-slurm-kw99l   xpk-def-app-profile                 1/1           5s         3h54m
    xpk-def-app-profile-slurm-x99nx   xpk-def-app-profile                 3/3           29s        17h
  ```

## Job Cancel

*   Job Cancel (delete job submitted via batch command):

    ```shell
    python3 xpk.py job cancel xpk-def-app-profile-slurm-74kbv --cluster xpk-test
    ```

## Inspector
* Inspector provides debug info to understand cluster health, and why workloads are not running.
Inspector output is saved to a file.

    ```shell
    python3 xpk.py inspector \
      --cluster $CLUSTER_NAME \
      --project $PROJECT_ID \
      --zone $ZONE
    ```

* Optional Arguments
  * `--print-to-terminal`:
    Print command output to terminal as well as a file.
  * `--workload $WORKLOAD_NAME`
    Inspector will write debug info related to the workload:`$WORKLOAD_NAME`

* Example Output:

  The output of xpk inspector is in `/tmp/tmp0pd6_k1o` in this example.
  ```shell
  [XPK] Starting xpk
  [XPK] Task: `Set Cluster` succeeded.
  [XPK] Task: `Local Setup: gcloud version` is implemented by `gcloud version`, hiding output unless there is an error.
  [XPK] Task: `Local Setup: Project / Zone / Region` is implemented by `gcloud config get project; gcloud config get compute/zone; gcloud config get compute/region`, hiding output unless there is an error.
  [XPK] Task: `GKE: Cluster Details` is implemented by `gcloud beta container clusters list --project $PROJECT --region $REGION | grep -e NAME -e $CLUSTER_NAME`, hiding output unless there is an error.
  [XPK] Task: `GKE: Node pool Details` is implemented by `gcloud beta container node-pools list --cluster $CLUSTER_NAME  --project=$PROJECT --region=$REGION`, hiding output unless there is an error.
  [XPK] Task: `Kubectl: All Nodes` is implemented by `kubectl get node -o custom-columns='NODE_NAME:metadata.name, READY_STATUS:.status.conditions[?(@.type=="Ready")].status, NODEPOOL:metadata.labels.cloud\.google\.com/gke-nodepool'`, hiding output unless there is an error.
  [XPK] Task: `Kubectl: Number of Nodes per Node Pool` is implemented by `kubectl get node -o custom-columns=':metadata.labels.cloud\.google\.com/gke-nodepool' | sort | uniq -c`, hiding output unless there is an error.
  [XPK] Task: `Kubectl: Healthy Node Count Per Node Pool` is implemented by `kubectl get node -o custom-columns='NODE_NAME:metadata.name, READY_STATUS:.status.conditions[?(@.type=="Ready")].status, NODEPOOL:metadata.labels.cloud\.google\.com/gke-nodepool' | grep -w True | awk {'print $3'} | sort | uniq -c`, hiding output unless there is an error.
  [XPK] Task: `Kueue: ClusterQueue Details` is implemented by `kubectl describe ClusterQueue cluster-queue`, hiding output unless there is an error.
  [XPK] Task: `Kueue: LocalQueue Details` is implemented by `kubectl describe LocalQueue multislice-queue`, hiding output unless there is an error.
  [XPK] Task: `Kueue: Kueue Deployment Details` is implemented by `kubectl describe Deployment kueue-controller-manager -n kueue-system`, hiding output unless there is an error.
  [XPK] Task: `Jobset: Deployment Details` is implemented by `kubectl describe Deployment jobset-controller-manager -n jobset-system`, hiding output unless there is an error.
  [XPK] Task: `Kueue Manager Logs` is implemented by `kubectl logs deployment/kueue-controller-manager -n kueue-system --tail=100 --prefix=True`, hiding output unless there is an error.
  [XPK] Task: `Jobset Manager Logs` is implemented by `kubectl logs deployment/jobset-controller-manager -n jobset-system --tail=100 --prefix=True`, hiding output unless there is an error.
  [XPK] Task: `List Jobs with filter-by-status=EVERYTHING with filter-by-jobs=None` is implemented by `kubectl get workloads -o=custom-columns="Jobset Name:.metadata.ownerReferences[0].name,Created Time:.metadata.creationTimestamp,Priority:.spec.priorityClassName,TPU VMs Needed:.spec.podSets[0].count,TPU VMs Running/Ran:.status.admission.podSetAssignments[-1].count,TPU VMs Done:.status.reclaimablePods[0].count,Status:.status.conditions[-1].type,Status Message:.status.conditions[-1].message,Status Time:.status.conditions[-1].lastTransitionTime"  `, hiding output unless there is an error.
  [XPK] Task: `List Jobs with filter-by-status=QUEUED with filter-by-jobs=None` is implemented by `kubectl get workloads -o=custom-columns="Jobset Name:.metadata.ownerReferences[0].name,Created Time:.metadata.creationTimestamp,Priority:.spec.priorityClassName,TPU VMs Needed:.spec.podSets[0].count,TPU VMs Running/Ran:.status.admission.podSetAssignments[-1].count,TPU VMs Done:.status.reclaimablePods[0].count,Status:.status.conditions[-1].type,Status Message:.status.conditions[-1].message,Status Time:.status.conditions[-1].lastTransitionTime"  | awk -e 'NR == 1 || ($7 ~ "Admitted|Evicted|QuotaReserved" && ($5 ~ "<none>" || $5 == 0)) {print $0}' `, hiding output unless there is an error.
  [XPK] Task: `List Jobs with filter-by-status=RUNNING with filter-by-jobs=None` is implemented by `kubectl get workloads -o=custom-columns="Jobset Name:.metadata.ownerReferences[0].name,Created Time:.metadata.creationTimestamp,Priority:.spec.priorityClassName,TPU VMs Needed:.spec.podSets[0].count,TPU VMs Running/Ran:.status.admission.podSetAssignments[-1].count,TPU VMs Done:.status.reclaimablePods[0].count,Status:.status.conditions[-1].type,Status Message:.status.conditions[-1].message,Status Time:.status.conditions[-1].lastTransitionTime"  | awk -e 'NR == 1 || ($7 ~ "Admitted|Evicted" && $5 ~ /^[0-9]+$/ && $5 > 0) {print $0}' `, hiding output unless there is an error.
  [XPK] Find xpk inspector output file: /tmp/tmp0pd6_k1o
  [XPK] Exiting XPK cleanly
  ```

## Run
* `xpk run` lets you execute scripts on a cluster with ease. It automates task execution, handles interruptions, and streams job output to your console.

  ```shell
  python xpk.py run --kind-cluster -n 2 -t 0-2 examples/job.sh 
  ```

* Example Output:

  ```shell
  [XPK] Starting xpk
  [XPK] Task: `get current-context` is implemented by `kubectl config current-context`, hiding output unless there is an error.
  [XPK] No local cluster name specified. Using current-context `kind-kind`
  [XPK] Task: `run task` is implemented by `kubectl kjob create slurm --profile xpk-def-app-profile --localqueue multislice-queue --wait --rm -- examples/job.sh --partition multislice-queue --ntasks 2 --time 0-2`. Streaming output and input live.
  job.batch/xpk-def-app-profile-slurm-g4vr6 created
  configmap/xpk-def-app-profile-slurm-g4vr6 created
  service/xpk-def-app-profile-slurm-g4vr6 created
  Starting log streaming for pod xpk-def-app-profile-slurm-g4vr6-1-4rmgk...
  Now processing task ID: 3
  Starting log streaming for pod xpk-def-app-profile-slurm-g4vr6-0-bg6dm...
  Now processing task ID: 1
  exit
  exit
  Now processing task ID: 2
  exit
  Job logs streaming finished.[XPK] Task: `run task` terminated with code `0`
  [XPK] XPK Done.
  ```

## GPU usage

In order to use XPK for GPU, you can do so by using `device-type` flag.

*   Cluster Create (provision reserved capacity):

    ```shell
    # Find your reservations
    gcloud compute reservations list --project=$PROJECT_ID

    # Run cluster create with reservation.
    python3 xpk.py cluster create \
    --cluster xpk-test --device-type=h100-80gb-8 \
    --num-nodes=2 \
    --reservation=$RESERVATION_ID
    ```

*   Cluster Delete (deprovision capacity):

    ```shell
    python3 xpk.py cluster delete \
    --cluster xpk-test
    ```

*   Cluster List (see provisioned capacity):

    ```shell
    python3 xpk.py cluster list
    ```

*   Cluster Describe (see capacity):

    ```shell
    python3 xpk.py cluster describe \
    --cluster xpk-test
    ```


*   Cluster Cacheimage (enables faster start times):

    ```shell
    python3 xpk.py cluster cacheimage \
    --cluster xpk-test --docker-image gcr.io/your_docker_image \
    --device-type=h100-80gb-8
    ```


*   [Install NVIDIA GPU device drivers](https://cloud.google.com/container-optimized-os/docs/how-to/run-gpus#install)
    ```shell
    # List available driver versions
    gcloud compute ssh $NODE_NAME --command "sudo cos-extensions list"

    # Install the default driver
    gcloud compute ssh $NODE_NAME --command "sudo cos-extensions install gpu"
    # OR install a specific version of the driver
    gcloud compute ssh $NODE_NAME --command "sudo cos-extensions install gpu -- -version=DRIVER_VERSION"
    ```

*   Run a workload:

    ```shell
    # Submit a workload
    python3 xpk.py workload create \
    --cluster xpk-test --device-type h100-80gb-8 \
    --workload xpk-test-workload \
    --command="echo hello world"
    ```

*   Workload Delete (delete training job):

    ```shell
    python3 xpk.py workload delete \
    --workload xpk-test-workload --cluster xpk-test
    ```

    This will only delete `xpk-test-workload` workload in `xpk-test` cluster.

*   Workload Delete (delete all training jobs in the cluster):

    ```shell
    python3 xpk.py workload delete \
    --cluster xpk-test
    ```

    This will delete all the workloads in `xpk-test` cluster. Deletion will only begin if you type `y` or `yes` at the prompt.

*   Workload Delete supports filtering. Delete a portion of jobs that match user criteria.
    * Filter by Job: `filter-by-job`

    ```shell
    python3 xpk.py workload delete \
    --cluster xpk-test --filter-by-job=$USER
    ```

    This will delete all the workloads in `xpk-test` cluster whose names start with `$USER`. Deletion will only begin if you type `y` or `yes` at the prompt.

    * Filter by Status: `filter-by-status`

    ```shell
    python3 xpk.py workload delete \
    --cluster xpk-test --filter-by-status=QUEUED
    ```

    This will delete all the workloads in `xpk-test` cluster that have the status as Admitted or Evicted, and the number of running VMs is 0. Deletion will only begin if you type `y` or `yes` at the prompt. Status can be: `EVERYTHING`,`FINISHED`, `RUNNING`, `QUEUED`, `FAILED`, `SUCCESSFUL`.

## CPU usage

In order to use XPK for CPU, you can do so by using `device-type` flag.

*   Cluster Create (provision on-demand capacity):

    ```shell
    # Run cluster create with on demand capacity.
    python3 xpk.py cluster create \
    --cluster xpk-test \
    --device-type=n2-standard-32-256 \
    --num-slices=1 \
    --default-pool-cpu-machine-type=n2-standard-32 \
    --on-demand
    ```
    Note that `device-type` for CPUs is of the format <cpu-machine-type>-<number of VMs>, thus in the above example, user requests for 256 VMs of type n2-standard-32.
    Currently workloads using < 1000 VMs are supported.

*   Run a workload:

    ```shell
    # Submit a workload
    python3 xpk.py workload create \
    --cluster xpk-test \
    --num-slices=1 \
    --device-type=n2-standard-32-256 \
    --workload xpk-test-workload \
    --command="echo hello world"
    ```

# Autoprovisioning with XPK
XPK can dynamically allocate cluster capacity using [Node Auto Provisioning, (NAP)](https://cloud.google.com/kubernetes-engine/docs/how-to/node-auto-provisioning#use_accelerators_for_new_auto-provisioned_node_pools) support.

Allow several topology sizes to be supported from one XPK cluster, and be dynamically provisioned based on incoming workload requests. XPK users will not need to re-provision the cluster manually.

Enabling autoprovisioning will take the cluster around initially up to **30 minutes to upgrade**.

## Create a cluster with autoprovisioning:

Autoprovisioning will be enabled on the below cluster with [0, 8] chips of v4 TPU (up to 1xv4-16) to scale
between.

XPK doesn't currently support different generations of accelerators in the same cluster (like v4 and v5p TPUs).

```shell
CLUSTER_NAME=my_cluster
NUM_SLICES=2
DEVICE_TYPE=v4-8
RESERVATION=reservation_id
PROJECT=my_project
ZONE=us-east5-b

python3 xpk.py cluster create \
  --cluster $CLUSTER_NAME \
  --num-slices=$NUM_SLICES \
    --device-type=$DEVICE_TYPE \
  --zone=$ZONE \
  --project=$PROJECT \
  --reservation=$RESERVATION \
  --enable-autoprovisioning
```

1. Define the starting accelerator configuration and capacity type.

    ```shell
    --device-type=$DEVICE_TYPE \
    --num-slice=$NUM_SLICES
    ```
2. Optionally set custom `minimum` / `maximum` chips. NAP will rescale the cluster with `maximum` - `minimum` chips. By default, `maximum` is set to the current cluster configuration size, and `minimum` is set to 0. This allows NAP to rescale with all the resources.

    ```shell
    --autoprovisioning-min-chips=$MIN_CHIPS \
    --autoprovisioning-max-chips=$MAX_CHIPS
    ```

3. `FEATURE TO COME SOON:` Set the timeout period for when node pools will automatically be deleted
if no incoming workloads are run. This is 10 minutes currently.

4. `FEATURE TO COME:` Set the timeout period to infinity. This will keep the idle node pool configuration always running until updated by new workloads.

### Update a cluster with autoprovisioning:
```shell
CLUSTER_NAME=my_cluster
NUM_SLICES=2
DEVICE_TYPE=v4-8
RESERVATION=reservation_id
PROJECT=my_project
ZONE=us-east5-b

python3 xpk.py cluster create \
  --cluster $CLUSTER_NAME \
  --num-slices=$NUM_SLICES \
    --device-type=$DEVICE_TYPE \
  --zone=$ZONE \
  --project=$PROJECT \
  --reservation=$RESERVATION \
  --enable-autoprovisioning
```

### Update a previously autoprovisioned cluster with different amount of chips:

* Option 1: By creating a new cluster nodepool configuration.

```shell
CLUSTER_NAME=my_cluster
NUM_SLICES=2
DEVICE_TYPE=v4-16
RESERVATION=reservation_id
PROJECT=my_project
ZONE=us-east5-b

# This will create 2x v4-16 node pools and set the max autoprovisioned chips to 16.
python3 xpk.py cluster create \
  --cluster $CLUSTER_NAME \
  --num-slices=$NUM_SLICES \
    --device-type=$DEVICE_TYPE \
  --zone=$ZONE \
  --project=$PROJECT \
  --reservation=$RESERVATION \
  --enable-autoprovisioning
```

* Option 2: By increasing the `--autoprovisioning-max-chips`.
```shell
CLUSTER_NAME=my_cluster
NUM_SLICES=0
DEVICE_TYPE=v4-16
RESERVATION=reservation_id
PROJECT=my_project
ZONE=us-east5-b

# This will clear the node pools if they exist in the cluster and set the max autoprovisioned chips to 16
python3 xpk.py cluster create \
  --cluster $CLUSTER_NAME \
  --num-slices=$NUM_SLICES \
    --device-type=$DEVICE_TYPE \
  --zone=$ZONE \
  --project=$PROJECT \
  --reservation=$RESERVATION \
  --enable-autoprovisioning \
  --autoprovisioning-max-chips 16
```

## Run workloads on the cluster with autoprovisioning:
Reconfigure the `--device-type` and `--num-slices`
  ```shell
  CLUSTER_NAME=my_cluster
  NUM_SLICES=2
  DEVICE_TYPE=v4-8
  NEW_RESERVATION=new_reservation_id
  PROJECT=my_project
  ZONE=us-east5-b
  # Create a 2x v4-8 TPU workload.
  python3 xpk.py workload create \
    --cluster $CLUSTER \
    --workload ${USER}-nap-${NUM_SLICES}x${DEVICE_TYPE}_$(date +%H-%M-%S) \
    --command "echo hello world from $NUM_SLICES $DEVICE_TYPE" \
    --device-type=$DEVICE_TYPE \
    --num-slices=$NUM_SLICES \
    --zone=$ZONE \
    --project=$PROJECT

  NUM_SLICES=1
  DEVICE_TYPE=v4-16

  # Create a 1x v4-16 TPU workload.
  python3 xpk.py workload create \
    --cluster $CLUSTER \
    --workload ${USER}-nap-${NUM_SLICES}x${DEVICE_TYPE}_$(date +%H-%M-%S) \
    --command "echo hello world from $NUM_SLICES $DEVICE_TYPE" \
    --device-type=$DEVICE_TYPE \
    --num-slices=$NUM_SLICES \
    --zone=$ZONE \
    --project=$PROJECT

  # Use a different reservation from what the cluster was created with.
  python3 xpk.py workload create \
    --cluster $CLUSTER \
    --workload ${USER}-nap-${NUM_SLICES}x${DEVICE_TYPE}_$(date +%H-%M-%S) \
    --command "echo hello world from $NUM_SLICES $DEVICE_TYPE" \
    --device-type=$DEVICE_TYPE \
    --num-slices=$NUM_SLICES \
    --zone=$ZONE \
    --project=$PROJECT \
    --reservation=$NEW_RESERVATION
  ```

1. (Optional) Define the capacity type. By default, the capacity type will
match with what the cluster was created with.

    ```shell
    --reservation=my-reservation-id | --on-demand | --spot
    ```

2. Set the topology of your workload using --device-type.

    ```shell
    NUM_SLICES=1
    DEVICE_TYPE=v4-8
    --device-type=$DEVICE_TYPE \
    --num-slices=$NUM_SLICES \
    ```


# How to add docker images to a xpk workload

The default behavior is `xpk workload create` will layer the local directory (`--script-dir`) into
the base docker image (`--base-docker-image`) and run the workload command.
If you don't want this layering behavior, you can directly use `--docker-image`. Do not mix arguments from the two flows in the same command.

## Recommended / Default Docker Flow: `--base-docker-image` and `--script-dir`
This flow pulls the `--script-dir` into the `--base-docker-image` and runs the new docker image.

* The below arguments are optional by default. xpk will pull the local
  directory with a generic base docker image.

  - `--base-docker-image` sets the base image that xpk will start with.

  - `--script-dir` sets which directory to pull into the image. This defaults to the current working directory.

  See `python3 xpk.py workload create --help` for more info.

* Example with defaults which pulls the local directory into the base image:
  ```shell
  echo -e '#!/bin/bash \n echo "Hello world from a test script!"' > test.sh
  python3 xpk.py workload create --cluster xpk-test \
  --workload xpk-test-workload-base-image --command "bash test.sh" \
  --tpu-type=v5litepod-16 --num-slices=1
  ```

* Recommended Flow For Normal Sized Jobs (fewer than 10k accelerators):
  ```shell
  python3 xpk.py workload create --cluster xpk-test \
  --workload xpk-test-workload-base-image --command "bash custom_script.sh" \
  --base-docker-image=gcr.io/your_dependencies_docker_image \
  --tpu-type=v5litepod-16 --num-slices=1
  ```

## Optional Direct Docker Image Configuration: `--docker-image`
If a user wants to directly set the docker image used and not layer in the
current working directory, set `--docker-image` to the image to be use in the
workload.

* Running with `--docker-image`:
  ```shell
  python3 xpk.py workload create --cluster xpk-test \
  --workload xpk-test-workload-base-image --command "bash test.sh" \
  --tpu-type=v5litepod-16 --num-slices=1 --docker-image=gcr.io/your_docker_image
  ```

* Recommended Flow For Large Sized Jobs (more than 10k accelerators):
  ```shell
  python3 xpk.py cluster cacheimage \
  --cluster xpk-test --docker-image gcr.io/your_docker_image
  # Run workload create with the same image.
  python3 xpk.py workload create --cluster xpk-test \
  --workload xpk-test-workload-base-image --command "bash test.sh" \
  --tpu-type=v5litepod-16 --num-slices=1 --docker-image=gcr.io/your_docker_image
  ```

# More advanced facts:

* Workload create has two mutually exclusive ways to override the environment of a workload:
  *  a `--env` flag to specify each environment variable separately. The format is:

     `--env VARIABLE1=value --env VARIABLE2=value`

  *  a `--env-file` flag to allow specifying the container's
environment from a file. Usage is the same as Docker's
[--env-file flag](https://docs.docker.com/engine/reference/commandline/run/#env)

    Example Env File:
    ```shell
    LIBTPU_INIT_ARGS=--my-flag=true --performance=high
    MY_ENV_VAR=hello
    ```

* Workload create accepts a --debug-dump-gcs flag which is a path to GCS bucket.
Passing this flag sets the XLA_FLAGS='--xla_dump_to=/tmp/xla_dump/' and uploads
hlo dumps to the specified GCS bucket for each worker.

# Integration Test Workflows
The repository code is tested through Github Workflows and Actions. Currently three kinds of tests are performed:
* A nightly build that runs every 24 hours
* A build that runs on push to `main` branch
* A build that runs for every PR approval

More information is documented [here](https://github.com/google/xpk/tree/main/.github/workflows)

# Troubleshooting

## `Invalid machine type` for CPUs.
XPK will create a regional GKE cluster. If you see issues like

```shell
Invalid machine type e2-standard-32 in zone $ZONE_NAME
```

Please select a CPU type that exists in all zones in the region.

```shell
# Find CPU Types supported in zones.
gcloud compute machine-types list --zones=$ZONE_LIST
# Adjust default cpu machine type.
python3 xpk.py cluster create --default-pool-cpu-machine-type=CPU_TYPE ...
```

## Workload creation fails

Some XPK cluster configuration might be missing, if workload creation fails with the below error.

`[XPK] b'error: the server doesn\'t have a resource type "workloads"\n'`

Mitigate this error by re-running your `xpk.py cluster create ...` command, to refresh the cluster configurations.

## Permission Issues: `requires one of ["permission_name"] permission(s)`.

1) Determine the role needed based on the permission error:

    ```shell
    # For example: `requires one of ["container.*"] permission(s)`
    # Add [Kubernetes Engine Admin](https://cloud.google.com/iam/docs/understanding-roles#kubernetes-engine-roles) to your user.
    ```

2) Add the role to the user in your project.

    Go to [iam-admin](https://console.cloud.google.com/iam-admin/) or use gcloud cli:
    ```shell
    PROJECT_ID=my-project-id
    CURRENT_GKE_USER=$(gcloud config get account)
    ROLE=roles/container.admin  # container.admin is the role needed for Kubernetes Engine Admin
    gcloud projects add-iam-policy-binding $PROJECT_ID --member user:$CURRENT_GKE_USER --role=$ROLE
    ```

3) Check the permissions are correct for the users.

    Go to [iam-admin](https://console.cloud.google.com/iam-admin/) or use gcloud cli:

    ```shell
    PROJECT_ID=my-project-id
    CURRENT_GKE_USER=$(gcloud config get account)
    gcloud projects get-iam-policy $PROJECT_ID --filter="bindings.members:$CURRENT_GKE_USER" --flatten="bindings[].members"
    ```

4) Confirm you have logged in locally with the correct user.

    ```shell
    gcloud auth login
    ```

### Roles needed based on permission errors:

* `requires one of ["container.*"] permission(s)`

  Add [Kubernetes Engine Admin](https://cloud.google.com/iam/docs/understanding-roles#kubernetes-engine-roles) to your user.

* `ERROR: (gcloud.monitoring.dashboards.list) User does not have permission to access projects instance (or it may not exist)`

  Add [Monitoring Viewer](https://cloud.google.com/iam/docs/understanding-roles#monitoring.viewer) to your user.


## Reservation Troubleshooting:

### How to determine your reservation and its size / utilization:

```shell
PROJECT_ID=my-project
ZONE=us-east5-b
RESERVATION=my-reservation-name
# Find the reservations in your project
gcloud beta compute reservations list --project=$PROJECT_ID
# Find the tpu machine type and current utilization of a reservation.
gcloud beta compute reservations describe $RESERVATION --project=$PROJECT_ID --zone=$ZONE
```

## 403 error on workload create when using `--base-docker-image` flag
You need authority to push to the registry from your local machine. Try running `gcloud auth configure-docker`.
## `Kubernetes API exception` - 404 error
If error of this kind appeared after updating xpk version it's possible that you need to rerun `cluster create` command in order to update resource definitions.

# TPU Workload Debugging

## Verbose Logging
If you are having trouble with your workload, try setting the `--enable-debug-logs` when you schedule it. This will give you more detailed logs to help pinpoint the issue. For example:
```shell
python3 xpk.py workload create \
--cluster --workload xpk-test-workload \
--command="echo hello world" --enable-debug-logs
```
Please check [libtpu logging](https://cloud.google.com/tpu/docs/troubleshooting/trouble-tf#debug_logs) and [Tensorflow logging](https://deepreg.readthedocs.io/en/latest/docs/logging.html#tensorflow-logging) for more information about the flags that are enabled to get the logs.

## Collect Stack Traces
[cloud-tpu-diagnostics](https://pypi.org/project/cloud-tpu-diagnostics/) PyPI package can be used to generate stack traces for workloads running in GKE. This package dumps the Python traces when a fault such as segmentation fault, floating-point exception, or illegal operation exception occurs in the program. Additionally, it will also periodically collect stack traces to help you debug situations when the program is unresponsive. You must make the following changes in the docker image running in a Kubernetes main container to enable periodic stack trace collection.
```shell
# main.py

from cloud_tpu_diagnostics import diagnostic
from cloud_tpu_diagnostics.configuration import debug_configuration
from cloud_tpu_diagnostics.configuration import diagnostic_configuration
from cloud_tpu_diagnostics.configuration import stack_trace_configuration

stack_trace_config = stack_trace_configuration.StackTraceConfig(
                      collect_stack_trace = True,
                      stack_trace_to_cloud = True)
debug_config = debug_configuration.DebugConfig(
                stack_trace_config = stack_trace_config)
diagnostic_config = diagnostic_configuration.DiagnosticConfig(
                      debug_config = debug_config)

with diagnostic.diagnose(diagnostic_config):
	main_method()  # this is the main method to run
```
This configuration will start collecting stack traces inside the `/tmp/debugging` directory on each Kubernetes Pod.

### Explore Stack Traces
To explore the stack traces collected in a temporary directory in Kubernetes Pod, you can run the following command to configure a sidecar container that will read the traces from `/tmp/debugging` directory.
 ```shell
 python3 xpk.py workload create \
  --workload xpk-test-workload --command "python3 main.py" --cluster \
  xpk-test --tpu-type=v5litepod-16 --deploy-stacktrace-sidecar
 ```

### Get information about jobs, queues and resources.

To list available resources and queues use ```xpk info``` command. It allows to see localqueues and clusterqueues and check for available resources.

To see queues with usage and workload info use:
```shell
python3 xpk.py info --cluster my-cluster
```

You can specify what kind of resources(clusterqueue or localqueue) you want to see using flags --clusterqueue or --localqueue.
```shell
python3 xpk.py info --cluster my-cluster --localqueue
```

# Local testing with Kind

To facilitate development and testing locally, we have integrated support for testing with `kind`. This enables you to simulate a Kubernetes environment on your local machine.

## Prerequisites

- Install kind on your local machine. Follow the official documentation here: [Kind Installation Guide.](https://kind.sigs.k8s.io/docs/user/quick-start#installation)

## Usage

xpk interfaces seamlessly with kind to manage Kubernetes clusters locally, facilitating the orchestration and management of workloads. Below are the commands for managing clusters:

### Cluster Create
*   Cluster create:

    ```shell
    python3 xpk.py kind create \
    --cluster xpk-test
    ```

### Cluster Delete
*   Cluster Delete:

    ```shell
    python3 xpk.py kind delete \
    --cluster xpk-test
    ```

### Cluster List
*   Cluster List:

    ```shell
    python3 xpk.py kind list
    ```

## Local Testing Basics

Local testing is available exclusively through the `batch` and `job` commands of xpk with the `--kind-cluster` flag. This allows you to simulate training jobs locally:

```shell
python xpk.py batch [other-options] --kind-cluster script
```

Please note that all other xpk subcommands are intended for use with cloud systems on Google Cloud Engine (GCE) and don't support local testing. This includes commands like cluster, info, inspector, etc.

# Other advanced usage
[Use a Jupyter notebook to interact with a Cloud TPU cluster](xpk-notebooks.md)
