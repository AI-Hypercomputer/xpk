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
 
## Workload Create
*   Workload Create (submit training job):

    ```shell
    xpk workload create \
    --workload xpk-test-workload --command "echo goodbye" \
    --cluster xpk-test \
    --tpu-type=v5litepod-16 --project=$PROJECT
    ```
*   Workload create (DWS flex with queued provisioning):
    ```shell
    xpk workload create \
    --workload xpk-test-workload --command "echo goodbye" \
    --cluster xpk-test  --flex \
    --tpu-type=v5litepod-16 --project=$PROJECT
    ```

*   Workload Create for Pathways:
    Pathways workload can be submitted using `workload create-pathways` on a Pathways enabled cluster (created with `cluster create-pathways`)

    Pathways workload example:
    ```shell
    xpk workload create-pathways \
    --workload xpk-pw-test \
    --num-slices=1 \
    --tpu-type=v5litepod-16 \
    --cluster xpk-pw-test \
    --docker-name='user-workload' \
    --docker-image=<maxtext docker image> \
    --command='python3 -m MaxText.train MaxText/configs/base.yml base_output_directory=<output directory> dataset_path=<dataset path> per_device_batch_size=1 enable_checkpointing=false enable_profiler=false remat_policy=full global_parameter_scale=4 steps=300 max_target_length=2048 use_iota_embed=true reuse_example_batch=1 dataset_type=synthetic attention=flash gcs_metrics=True run_name=$(USER)-pw-xpk-test-1 enable_single_controller=True'
    ```

    Regular workload can also be submitted on a Pathways enabled cluster (created with `cluster create-pathways`)

    Pathways workload example:
    ```shell
    xpk workload create-pathways \
    --workload xpk-regular-test \
    --num-slices=1 \
    --tpu-type=v5litepod-16 \
    --cluster xpk-pw-test \
    --docker-name='user-workload' \
    --docker-image=<maxtext docker image> \
    --command='python3 -m MaxText.train MaxText/configs/base.yml base_output_directory=<output directory> dataset_path=<dataset path> per_device_batch_size=1 enable_checkpointing=false enable_profiler=false remat_policy=full global_parameter_scale=4 steps=300 max_target_length=2048 use_iota_embed=true reuse_example_batch=1 dataset_type=synthetic attention=flash gcs_metrics=True run_name=$(USER)-pw-xpk-test-1'
    ```

    Pathways in headless mode - Pathways now offers the capability to run JAX workloads in Vertex AI notebooks or in GCE VMs!
    Specify `--headless` with `workload create-pathways` when the user workload is not provided in a docker container.
    ```shell
    xpk workload create-pathways --headless \
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

* `--max-restarts <value>`: By default, this is 0. This will restart the job "" times when the job terminates. For production jobs, it is recommended to
increase this to a large number, say 50. Real jobs can be interrupted due to
hardware failures and software updates. We assume your job has implemented
checkpointing so the job restarts near where it was interrupted.

### Workloads for A3 Ultra, A3 Mega and A4 clusters (GPU machines)
To submit jobs on a cluster with A3 or A4 machines, run the command with selected device type. To create a cluster with A3 or A4 machines see [here](./clusters.md#provisioning-a3-ultra-a3-mega-and-a4-clusters-gpu-machines).


Machine | Device type
:- | :-
A3 Mega | `h100-mega-80gb-8`
A3 Ultra | `h200-141gb-8`
A4 | `b200-8`

```shell
xpk workload create \
  --workload=$WORKLOAD_NAME --command="echo goodbye" \
  --cluster=$CLUSTER_NAME --device-type DEVICE_TYPE \
  --zone=$COMPUTE_ZONE  --project=$PROJECT_ID \
  --num-nodes=$WOKRKLOAD_NUM_NODES
```

> The docker image flags/arguments introduced in [workloads section](#workload-create) can be used with A3 or A4 machines as well.

In order to run NCCL test on A3 machines check out [this guide](../../examples/nccl/nccl.md).

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
      xpk workload create \
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
xpk workload create \
--cluster xpk-test --workload xpk-workload \
--use-vertex-tensorboard
```

will create a Vertex AI Experiment with the name `xpk-test-xpk-workload` (*<args.cluster>-<args.workload>*).

* Create Vertex AI Experiment with user-specified Experiment name:

```shell
xpk workload create \
--cluster xpk-test --workload xpk-workload \
--use-vertex-tensorboard --experiment-name=test-experiment
```

will create a Vertex AI Experiment with the name `test-experiment`.

Check out [MaxText example](https://github.com/google/maxtext/pull/570) on how to update your workload to automatically upload logs collected in your Tensorboard directory to the Vertex AI Experiment created by `workload create`.

## Workload Delete
*   Workload Delete (delete training job):

    ```shell
    xpk workload delete \
    --workload xpk-test-workload --cluster xpk-test
    ```

    This will only delete `xpk-test-workload` workload in `xpk-test` cluster.

*   Workload Delete (delete all training jobs in the cluster):

    ```shell
    xpk workload delete \
    --cluster xpk-test
    ```

    This will delete all the workloads in `xpk-test` cluster. Deletion will only begin if you type `y` or `yes` at the prompt. Multiple workload deletions are processed in batches for optimized processing.

*   Workload Delete supports filtering. Delete a portion of jobs that match user criteria.
    * Filter by Job: `filter-by-job`

    ```shell
    xpk workload delete \
    --cluster xpk-test --filter-by-job=$USER
    ```

    This will delete all the workloads in `xpk-test` cluster whose names start with `$USER`. Deletion will only begin if you type `y` or `yes` at the prompt.

    * Filter by Status: `filter-by-status`

    ```shell
    xpk workload delete \
    --cluster xpk-test --filter-by-status=QUEUED
    ```

    This will delete all the workloads in `xpk-test` cluster that have the status as Admitted or Evicted, and the number of running VMs is 0. Deletion will only begin if you type `y` or `yes` at the prompt. Status can be: `EVERYTHING`,`FINISHED`, `RUNNING`, `QUEUED`, `FAILED`, `SUCCESSFUL`.

## Workload List
*   Workload List (see training jobs):

    ```shell
    xpk workload list \
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
    xpk workload list \
    --cluster xpk-test --filter-by-job=$USER
    ```

* Workload List supports waiting for the completion of a specific job. XPK will follow an existing job until it has finished or the `timeout`, if provided, has been reached  and then list the job. If no `timeout` is specified, the default value is set to the max value, 1 week. You may also set `timeout=0` to poll the job once.

  Wait for a job to complete.

    ```shell
    xpk workload list \
    --cluster xpk-test --wait-for-job-completion=xpk-test-workload
    ```

  Wait for a job to complete with a timeout of 300 seconds.

    ```shell
    xpk workload list \
    --cluster xpk-test --wait-for-job-completion=xpk-test-workload \
    --timeout=300
    ```

  Return codes
    `0`: Workload finished and completed successfully.
    `124`: Timeout was reached before workload finished.
    `125`: Workload finished but did not complete successfully.
    `1`: Other failure.
