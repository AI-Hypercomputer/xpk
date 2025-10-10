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

xpk cluster create \
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

xpk cluster create \
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
xpk cluster create \
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
xpk cluster create \
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
xpk workload create \
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
xpk workload create \
    --cluster $CLUSTER \
    --workload ${USER}-nap-${NUM_SLICES}x${DEVICE_TYPE}_$(date +%H-%M-%S) \
    --command "echo hello world from $NUM_SLICES $DEVICE_TYPE" \
    --device-type=$DEVICE_TYPE \
    --num-slices=$NUM_SLICES \
    --zone=$ZONE \
    --project=$PROJECT

# Use a different reservation from what the cluster was created with.
xpk workload create \
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

