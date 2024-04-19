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

and the following GPU types:
* a100
* h100

and the following CPU types:
* n2-standard-32

# Installation
To install xpk, run the following command:

```shell
pip install xpk
```

If you are running XPK by cloning GitHub repository, first run the
following commands to begin using XPK commands:

```shell
git clone https://github.com/google/xpk.git
cd xpk
# Install dependencies such as cloud-accelerator-diagnostics
pip install .
```

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
  # Install dependencies such as cloud-accelerator-diagnostics
  pip install .
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
    Pathways compatible cluster can be created using `--enable-pathways`
    ```shell
    python3 xpk.py cluster create \
    --cluster xpk-pw-test \
    --num-slices=4 --on-demand \
    --tpu-type=v5litepod-16 \
    --enable-pathways
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

## Workload Create
*   Workload Create (submit training job):

    ```shell
    python3 xpk.py workload create \
    --workload xpk-test-workload --command "echo goodbye" \
    --cluster xpk-test \
    --tpu-type=v5litepod-16
    ```

*   Workload Create for Pathways:
    Pathways workload can be submitted using `--use-pathways` on a Pathways enabled cluster (created with `--enable-pathways`)

    Pathways workload example:
    ```shell
    python3 xpk.py workload create \
    --workload xpk-pw-test \
    --num-slices=1 \
    --tpu-type=v5litepod-16 \
    --use-pathways \
    --cluster xpk-pw-test \
    --docker-name='user-workload' \
    --docker-image=<maxtext docker image> \
    --command='python3 MaxText/train.py MaxText/configs/base.yml base_output_directory=<output directory> dataset_path=<dataset path> per_device_batch_size=1 enable_checkpointing=false enable_profiler=false remat_policy=full global_parameter_scale=4 steps=300 max_target_length=2048 use_iota_embed=true reuse_example_batch=1 dataset_type=synthetic attention=flash gcs_metrics=True run_name=$(USER)-pw-xpk-test-1'
    ```

    Regular workload can also be submitted on a Pathways enabled cluster (created with `--enable-pathways`)

    Pathways workload example:
    ```shell
    python3 xpk.py workload create \
    --workload xpk-regular-test \
    --num-slices=1 \
    --tpu-type=v5litepod-16 \
    --cluster xpk-pw-test \
    --docker-name='user-workload' \
    --docker-image=<maxtext docker image> \
    --command='python3 MaxText/train.py MaxText/configs/base.yml base_output_directory=<output directory> dataset_path=<dataset path> per_device_batch_size=1 enable_checkpointing=false enable_profiler=false remat_policy=full global_parameter_scale=4 steps=300 max_target_length=2048 use_iota_embed=true reuse_example_batch=1 dataset_type=synthetic attention=flash gcs_metrics=True run_name=$(USER)-pw-xpk-test-1'
    ```

### Set `max-restarts` for production jobs

* `--max-restarts <value>`: By default, this is 0. This will restart the job ""
times when the job terminates. For production jobs, it is recommended to
increase this to a large number, say 50. Real jobs can be interrupted due to
hardware failures and software updates. We assume your job has implemented
checkpointing so the job restarts near where it was interrupted.

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
(Note: `restart-on-user-code-failure` must be set
when creating the workload otherwise the workload will always finish with `Completed` status.)

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
