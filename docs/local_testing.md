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
 
# Local testing with Kind

To facilitate development and testing locally, we have integrated support for testing with `kind`. This enables you to simulate a Kubernetes environment on your local machine.

## Prerequisites

- Install kind on your local machine. Follow the official documentation here: [Kind Installation Guide.](https://kind.sigs.k8s.io/docs/user/quick-start#installation)

## Usage

xpk interfaces seamlessly with kind to manage Kubernetes clusters locally, facilitating the orchestration and management of workloads. Below are the commands for managing clusters:

### Cluster Create
*   Cluster create:

    ```shell
    xpk kind create \
    --cluster xpk-test
    ```

### Cluster Delete
*   Cluster Delete:

    ```shell
    xpk kind delete \
    --cluster xpk-test
    ```

### Cluster List
*   Cluster List:

    ```shell
    xpk kind list
    ```

## Local Testing Basics

Local testing is available exclusively through the `batch` and `job` commands of xpk with the `--kind-cluster` flag. This allows you to simulate training jobs locally:

```shell
python xpk.py batch [other-options] --kind-cluster script
```

Please note that all other xpk subcommands are intended for use with cloud systems on Google Cloud Engine (GCE) and don't support local testing. This includes commands like cluster, info, inspector, etc.

