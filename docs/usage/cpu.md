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

## CPU usage

In order to use XPK for CPU, you can do so by using `device-type` flag.

*   Cluster Create (provision on-demand capacity):

    ```shell
    # Run cluster create with on demand capacity.
    xpk cluster create \
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
    xpk workload create \
    --cluster xpk-test \
    --num-slices=1 \
    --device-type=n2-standard-32-256 \
    --workload xpk-test-workload \
    --command="echo hello world"
    ```

