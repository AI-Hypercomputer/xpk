
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

