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
 
## GPU usage

In order to use XPK for GPU, you can do so by using `device-type` flag.

*   Cluster Create (provision reserved capacity):

    ```shell
    # Find your reservations
    gcloud compute reservations list --project=$PROJECT_ID

    # Run cluster create with reservation.
    xpk cluster create \
    --cluster xpk-test --device-type=h100-80gb-8 \
    --num-nodes=2 \
    --reservation=$RESERVATION_ID
    ```

*   Cluster Delete (deprovision capacity):

    ```shell
    xpk cluster delete \
    --cluster xpk-test
    ```

*   Cluster List (see provisioned capacity):

    ```shell
    xpk cluster list
    ```

*   Cluster Describe (see capacity):

    ```shell
    xpk cluster describe \
    --cluster xpk-test
    ```


*   Cluster Cacheimage (enables faster start times):

    ```shell
    xpk cluster cacheimage \
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
    xpk workload create \
    --cluster xpk-test --device-type h100-80gb-8 \
    --workload xpk-test-workload \
    --command="echo hello world"
    ```

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

    This will delete all the workloads in `xpk-test` cluster. Deletion will only begin if you type `y` or `yes` at the prompt.

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
