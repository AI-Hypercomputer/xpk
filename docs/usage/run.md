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
