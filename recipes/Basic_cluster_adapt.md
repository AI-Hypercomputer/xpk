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
[XPK] Task: `Find cluster region or zone` is implemented by the following command not running since it is a dry run. 
gcloud container clusters list --project=golden-project --filter=name=golden-cluster --format="value(location)"
[XPK] Task: `get-credentials-dns-endpoint to cluster golden-cluster` is implemented by the following command not running since it is a dry run. 
gcloud container clusters get-credentials golden-cluster --location=us-central1 --dns-endpoint --project=golden-project && kubectl config view && kubectl config set-context --current --namespace=default
[XPK] Task: `Test kubectl credentials` is implemented by the following command not running since it is a dry run. 
kubectl get pods
[XPK] Finished get-credentials and kubectl setup.
[XPK] Creating ConfigMap for cluster
[XPK] Temp file (0604d72ef175c94fc796d8f02cff009b4241e85d444d22d414a56a47764d7bbb) content: 
kind: ConfigMap
apiVersion: v1
metadata:
  name: golden-cluster-resources-configmap
data:
  tpu7x-8: "1"

[XPK] Temp file (98d12ea0d3ca6d78cd064743373371c479127d21c7c9d01317e5e2d2d8c0b075) content: 
kind: ConfigMap
apiVersion: v1
metadata:
  name: golden-cluster-metadata-configmap
data:
  xpk_version: v0.0.0
  capacity_type: UNKNOWN

[XPK] Breaking up a total of 2 commands into 1 batches
[XPK] Pretending all the jobs succeeded
[XPK] Enabling the jobset API on our cluster, to be deprecated when Jobset is globally available
[XPK] Try 1: Install Jobset on golden-cluster
[XPK] Task: `Install Jobset on golden-cluster` is implemented by the following command not running since it is a dry run. 
kubectl apply --server-side --force-conflicts -f https://github.com/kubernetes-sigs/jobset/releases/download/v0.8.0/manifests.yaml
[XPK] Enabling Kueue on the cluster
[XPK] Task: `Get kueue version on server` is implemented by the following command not running since it is a dry run. 
kubectl get deployment kueue-controller-manager -n kueue-system -o jsonpath='{.spec.template.spec.containers[0].image}'
[XPK] Installing Kueue version v0.15.2...
[XPK] Try 1: Install Kueue
[XPK] Task: `Install Kueue` is implemented by the following command not running since it is a dry run. 
kubectl apply --server-side --force-conflicts -f https://github.com/kubernetes-sigs/kueue/releases/download/v0.15.2/manifests.yaml
[XPK] Task: `Wait for Kueue to be available` is implemented by the following command not running since it is a dry run. 
kubectl wait deploy/kueue-controller-manager -n kueue-system --for=condition=available --timeout=10m
[XPK] Temp file (6083d72fc3ba2ac7d243c1269dd67717abd4086bf64e397e3a1737de415dd133) content: 

apiVersion: kueue.x-k8s.io/v1beta1
kind: ResourceFlavor
metadata:
  name: "1xtpu7x-8"
spec:
  nodeLabels: {"cloud.google.com/gke-tpu-accelerator": "tpu7x", "cloud.google.com/gke-tpu-topology": "2x2x1"}
---
apiVersion: kueue.x-k8s.io/v1beta1
kind: ProvisioningRequestConfig
metadata:
  name: dws-config
spec:
  provisioningClassName: queued-provisioning.gke.io
  podSetUpdates:
    nodeSelector:
    - key: autoscaling.gke.io/provisioning-request
      valueFromProvisioningClassDetail: ResizeRequestName
  managedResources:
  - google.com/tpu
---
apiVersion: kueue.x-k8s.io/v1beta1
kind: ClusterQueue
metadata:
  name: "cluster-queue"
spec:
  preemption:
    reclaimWithinCohort: Never # Don't preempt other queues in the cohort.
    withinClusterQueue: LowerPriority
  namespaceSelector: {} # match all.
  resourceGroups: [{'coveredResources': ['google.com/tpu'], 'flavors': [{'name': '1xtpu7x-8', 'resources': [{'name': 'google.com/tpu', 'nominalQuota': 4}]}]}]
---
apiVersion: kueue.x-k8s.io/v1beta1
kind: LocalQueue
metadata:
  namespace: default
  name: multislice-queue
spec:
  clusterQueue: cluster-queue
---
apiVersion: scheduling.k8s.io/v1
kind: PriorityClass
metadata:
  name: very-low
value: 100
globalDefault: false
description: "Very Low"
---
apiVersion: scheduling.k8s.io/v1
kind: PriorityClass
metadata:
  name: low
value: 250
globalDefault: false
description: "Low"
---
apiVersion: scheduling.k8s.io/v1
kind: PriorityClass
metadata:
  name: medium
value: 500
globalDefault: false
description: "Medium"
---
apiVersion: scheduling.k8s.io/v1
kind: PriorityClass
metadata:
  name: high
value: 750
globalDefault: false
description: "High"
---
apiVersion: scheduling.k8s.io/v1
kind: PriorityClass
metadata:
  name: very-high
value: 1000
globalDefault: false
description: "Very High"
[XPK] Task: `Applying Kueue Custom Resources` is implemented by the following command not running since it is a dry run. 
kubectl apply -f 6083d72fc3ba2ac7d243c1269dd67717abd4086bf64e397e3a1737de415dd133
[XPK] Task: `Count total nodes` is implemented by the following command not running since it is a dry run. 
kubectl get node --no-headers | wc -l
[XPK] Try 1: Updating Kueue Controller Manager resources
[XPK] Task: `Updating Kueue Controller Manager resources` is implemented by the following command not running since it is a dry run. 
kubectl patch deployment kueue-controller-manager -n kueue-system --type='strategic' --patch='{"spec": {"template": {"spec": {"containers": [{"name": "manager", "resources": {"limits": {"memory": "4096Mi"}}}]}}}}'
[XPK] GKE commands done! Resources are created.
[XPK] See your GKE Cluster here: https://console.cloud.google.com/kubernetes/clusters/details/us-central1/golden-cluster/details?project=golden-project
[XPK] Exiting XPK cleanly
-->
