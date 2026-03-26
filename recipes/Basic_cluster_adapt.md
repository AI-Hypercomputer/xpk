# Basic cluster adapt
Adapts an existing GKE cluster for XPK by installing Jobset, Kueue, and other dependencies.

# Running the command
```shell #golden
xpk cluster adapt --project=golden-project --zone=us-central1-a --cluster=golden-cluster --tpu-type=tpu7x-8
```
<!--
$ xpk cluster adapt --project=golden-project --zone=us-central1-a --cluster=golden-cluster --tpu-type=tpu7x-8
[XPK] Starting xpk v0.0.0
[XPK] Starting cluster adaptation for cluster golden-cluster:
[XPK] Working on golden-project and us-central1-a
[XPK] Argument --num-slices was not provided, trying to determine number of slices based on the available nodepools in the cluster...
[XPK] Task: `Find cluster region or zone` is implemented by the following command not running since it is a dry run. 
gcloud container clusters list --project=golden-project --filter=name=golden-cluster --format="value(location)"
[XPK] Task: `Get All Node Pools` is implemented by the following command not running since it is a dry run. 
gcloud beta container node-pools list --cluster golden-cluster --project=golden-project --location=us-central1 --format="csv[no-heading](name)"
[XPK] Found unexpected number of slices (0). Ensure the cluster exists and was created by XPK.
[XPK] XPK failed, error code 1
-->
