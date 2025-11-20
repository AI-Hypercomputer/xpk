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
    xpk cluster create \
    --cluster xpk-test --tpu-type=v5litepod-256 \
    --num-slices=2 \
    --reservation=$RESERVATION_ID
    ```

*   Cluster Create (provision on-demand capacity):

    ```shell
    xpk cluster create \
    --cluster xpk-test --tpu-type=v5litepod-16 \
    --num-slices=4 --on-demand
    ```

*   Cluster Create (provision spot / preemptable capacity):

    ```shell
    xpk cluster create \
    --cluster xpk-test --tpu-type=v5litepod-16 \
    --num-slices=4 --spot
    ```

* Cluster Create (DWS flex queued capacity):
    ```shell
        xpk cluster create \
        --cluster xpk-test --tpu-type=v5litepod-16 \
        --num-slices=4 --flex
    ```

*   Cluster Create with CPU and/or memory quota:
    ```shell
    xpk cluster create \
    --cluster xpk-test --tpu-type=v5litepod-16 \
    --cpu-limit=112 --memory-limit=192Gi \
    --on-demand
    ```

* Cluster Create for Pathways:
Pathways compatible cluster can be created using `cluster create-pathways`.
    ```shell
    xpk cluster create-pathways \
    --cluster xpk-pw-test \
    --num-slices=4 --on-demand \
    --tpu-type=v5litepod-16
    ```
    Note that Pathways clusters need a CPU nodepool of n2-standard-64 or higher.

*   Cluster Create for Ray:
    A cluster with KubeRay enabled and a RayCluster can be created using `cluster create-ray`.
    ```shell
    xpk cluster create-ray \
    --cluster xpk-rc-test \
    --ray-version=2.39.0 \
    --num-slices=4 --on-demand \
    --tpu-type=v5litepod-8
    ```

*   Cluster Create can be called again with the same `--cluster name` to modify
    the number of slices or retry failed steps.

    For example, if a user creates a cluster with 4 slices:

    ```shell
    xpk cluster create \
    --cluster xpk-test --tpu-type=v5litepod-16 \
    --num-slices=4  --reservation=$RESERVATION_ID
    ```

    and recreates the cluster with 8 slices. The command will rerun to create 4
    new slices:

    ```shell
    xpk cluster create \
    --cluster xpk-test --tpu-type=v5litepod-16 \
    --num-slices=8  --reservation=$RESERVATION_ID
    ```

    and recreates the cluster with 6 slices. The command will rerun to delete 2
    slices. The command will warn the user when deleting slices.
    Use `--force` to skip prompts.

    ```shell
    xpk cluster create \
    --cluster xpk-test --tpu-type=v5litepod-16 \
    --num-slices=6  --reservation=$RESERVATION_ID

    # Skip delete prompts using --force.

    xpk cluster create --force \
    --cluster xpk-test --tpu-type=v5litepod-16 \
    --num-slices=6  --reservation=$RESERVATION_ID
    ```

    and recreates the cluster with 4 slices of v4-8. The command will rerun to delete
    6 slices of v5litepod-16 and create 4 slices of v4-8. The command will warn the
    user when deleting slices. Use `--force` to skip prompts.

    ```shell
    xpk cluster create \
    --cluster xpk-test --tpu-type=v4-8 \
    --num-slices=4  --reservation=$RESERVATION_ID

    # Skip delete prompts using --force.

    xpk cluster create --force \
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
  xpk cluster create \
    --cluster=xpk-private-cluster \
    --tpu-type=v4-8 --num-slices=2 \
    --private
  ```

* To create a private cluster and allow access to Control Plane only to your current machine and the IP ranges `1.2.3.0/24` and `1.2.4.5/32`:

  ```shell
  xpk cluster create \
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
xpk cluster create \
--cluster xpk-test --num-slices=1 --tpu-type=v4-8 \
--create-vertex-tensorboard
```

will create a Vertex AI Tensorboard with the name `xpk-test-tb-instance` (*<args.cluster>-tb-instance*) in `us-central1` (*default region*).

* Create Vertex AI Tensorboard in user-specified region with default Tensorboard name:

```shell
xpk cluster create \
--cluster xpk-test --num-slices=1 --tpu-type=v4-8 \
--create-vertex-tensorboard --tensorboard-region=us-west1
```

will create a Vertex AI Tensorboard with the name `xpk-test-tb-instance` (*<args.cluster>-tb-instance*) in `us-west1`.

* Create Vertex AI Tensorboard in default region with user-specified Tensorboard name:

```shell
xpk cluster create \
--cluster xpk-test --num-slices=1 --tpu-type=v4-8 \
--create-vertex-tensorboard --tensorboard-name=tb-testing
```

will create a Vertex AI Tensorboard with the name `tb-testing` in `us-central1`.

* Create Vertex AI Tensorboard in user-specified region with user-specified Tensorboard name:

```shell
xpk cluster create \
--cluster xpk-test --num-slices=1 --tpu-type=v4-8 \
--create-vertex-tensorboard --tensorboard-region=us-west1 --tensorboard-name=tb-testing
```

will create a Vertex AI Tensorboard instance with the name `tb-testing` in `us-west1`.

* Create Vertex AI Tensorboard in an unsupported region:

```shell
xpk cluster create \
--cluster xpk-test --num-slices=1 --tpu-type=v4-8 \
--create-vertex-tensorboard --tensorboard-region=us-central2
```

will fail the cluster creation process because Vertex AI Tensorboard is not supported in `us-central2`.

## Cluster Delete
*   Cluster Delete (deprovision capacity):

    ```shell
    xpk cluster delete \
    --cluster xpk-test
    ```
## Cluster List
*   Cluster List (see provisioned capacity):

    ```shell
    xpk cluster list
    ```
## Cluster Describe
*   Cluster Describe (see capacity):

    ```shell
    xpk cluster describe \
    --cluster xpk-test
    ```

## Cluster Cacheimage
*   Cluster Cacheimage (enables faster start times):

    ```shell
    xpk cluster cacheimage \
    --cluster xpk-test --docker-image gcr.io/your_docker_image \
    --tpu-type=v5litepod-16
    ```

## Provisioning A3 Ultra, A3 Mega and A4 clusters (GPU machines)
To create a cluster with A3 or A4 machines, run the command below with selected device type. To create workloads on these clusters see [here](#workloads-for-a3-ultra-a3-mega-and-a4-clusters-gpu-machines).

**Note:** Creating A3 Ultra, A3 Mega and A4 clusters is currently supported **only** on linux/amd64 architecture.

Machine | Device type
:- | :-
A3 Mega | `h100-mega-80gb-8`
A3 Ultra | `h200-141gb-8`
A4 | `b200-8`


```shell
xpk cluster create \
  --cluster CLUSTER_NAME --device-type DEVICE_TYPE \
  --zone=$COMPUTE_ZONE  --project=$PROJECT_ID \
  --num-nodes=$NUM_NODES --reservation=$RESERVATION_ID
```

Currently, the below flags/arguments are supported for A3 Mega, A3 Ultra and A4 machines:
  * `--num-nodes`
  * `--default-pool-cpu-machine-type`
  * `--default-pool-cpu-num-nodes`
  * `--reservation`
  * `--spot`
  * `--on-demand` (A3 Mega only)
  * `--flex`

## Running XPK on existing clusters

In order to run XPK commands on a cluster it needs to be set up correctly. This is done automatically when creating a cluster using `xpk cluster create`. For clusters created differently (e.g.: with 'gcloud' or a Cluster Toolkit blueprint) there is a dedicated command: `xpk cluster adapt`. This command installs required config maps, kueue, jobset, CSI drivers etc.

Currently `xpk cluster adapt` supports only the following device types:

- `h200-141gb-8` (A3 Ultra)

Example usage: 
```shell
xpk cluster adapt \
  --cluster=$CLUSTER_NAME --device-type=$DEVICE_TYPE \
  --zone=$COMPUTE_ZONE  --project=$PROJECT_ID \
  --num-nodes=$NUM_NODES --reservation=$RESERVATION_ID
```
