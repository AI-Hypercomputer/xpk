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
xpk cluster create --default-pool-cpu-machine-type=CPU_TYPE ...
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
xpk workload create \
--cluster --workload xpk-test-workload \
--command="echo hello world" --enable-debug-logs
```
Please check [libtpu logging](https://cloud.google.com/tpu/docs/troubleshooting/trouble-tf#debug_logs) and [Tensorflow logging](https://deepreg.readthedocs.io/en/latest/logging.html#tensorflow-logging) for more information about the flags that are enabled to get the logs.

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
xpk workload create \
  --workload xpk-test-workload --command "python3 main.py" --cluster \
  xpk-test --tpu-type=v5litepod-16 --deploy-stacktrace-sidecar
 ```

### Get information about jobs, queues and resources.

To list available resources and queues use ```xpk info``` command. It allows to see localqueues and clusterqueues and check for available resources.

To see queues with usage and workload info use:
```shell
xpk info --cluster my-cluster
```

You can specify what kind of resources(clusterqueue or localqueue) you want to see using flags --clusterqueue or --localqueue.
```shell
xpk info --cluster my-cluster --localqueue
```

```
