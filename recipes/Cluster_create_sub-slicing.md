# Cluster create sub-slicing
Creates a GKE cluster with TPU sub-slicing enabled for fractional chip usage.

# Running the command
```shell #golden
SUB_SLICING_ENABLED=true xpk cluster create --project=golden-project --zone=us-central1-a --cluster=golden-cluster --tpu-type=v6e-4x4 --reservation=golden-reservation --sub-slicing
```
<!--
$ SUB_SLICING_ENABLED=true xpk cluster create --project=golden-project --zone=us-central1-a --cluster=golden-cluster --tpu-type=v6e-4x4 --reservation=golden-reservation --sub-slicing
[XPK] Starting xpk v0.0.0
[XPK] Starting cluster create for cluster golden-cluster:
[XPK] Working on golden-project and us-central1-a
[XPK] Task: `Get reservation golden-reservation` is implemented by the following command not running since it is a dry run. 
gcloud beta compute reservations describe golden-reservation --project=golden-project --zone=us-central1-a --format="json(specificReservation,aggregateReservation,status,deploymentType,resourcePolicies)"
[XPK] Assessing reservation capacity...
[XPK] ERROR: Reservation golden-reservation has no available capacity.
[XPK] Error assessing available slices.
[XPK] XPK failed, error code 1
-->
