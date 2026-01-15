# Comprehensive XPK Recipe Demo

This recipe demonstrates the capabilities of the XPK recipe executor (`tools/recipes.py`).
Feel free to use it for testing with following commands:
- `python3 tools/recipes.py update recipes/comprehensive-demo.md` - updates this recipe file
- `python3 tools/recipes.py golden recipes/comprehensive-demo.md` - verifies modified outputs against this file
- `python3 tools/recipes.py run recipes/comprehensive-demo.md` - runs recipe's commands

## 1. Run only cells
This cell will only get executed during run mode. It will not get golden computed.

```shell
echo "Hello world!"
```


## 2. Environment Persistence
Variables exported in one block are available in subsequent blocks.

```shell #golden
export DEMO_VAR="Hello from Block 1"
echo "Set DEMO_VAR"
```
<!--
$ export DEMO_VAR="Hello from Block 1"
echo "Set DEMO_VAR"
Set DEMO_VAR
-->

```shell #golden
echo "Reading DEMO_VAR: $DEMO_VAR"
```
<!--
$ echo "Reading DEMO_VAR: $DEMO_VAR"
Reading DEMO_VAR: Hello from Block 1
-->

## 3. Function Persistence
XPK is correctly executed in dry-run mode.

```shell #golden
xpk workload list --cluster=foo --project=bar --zone=us-central1-a
```
<!--
$ xpk workload list --cluster=foo --project=bar --zone=us-central1-a
[XPK] Starting xpk v0.0.0
[XPK] Starting workload list
[XPK] Working on bar and us-central1-a
[XPK] Task: `Find cluster region or zone` is implemented by the following command not running since it is a dry run. 
gcloud container clusters list --project=bar --filter=name=foo --format="value(location)"
[XPK] Task: `get-credentials-dns-endpoint to cluster foo` is implemented by the following command not running since it is a dry run. 
gcloud container clusters get-credentials foo --location=us-central1 --dns-endpoint --project=bar && kubectl config view && kubectl config set-context --current --namespace=default
[XPK] Task: `Test kubectl credentials` is implemented by the following command not running since it is a dry run. 
kubectl get pods
[XPK] Finished get-credentials and kubectl setup.
[XPK] Task: `List Jobs with filter-by-status=EVERYTHING with filter-by-job=None` is implemented by the following command not running since it is a dry run. 
kubectl get workloads --ignore-not-found -o=custom-columns="Jobset Name:.metadata.ownerReferences[0].name,Created Time:.metadata.creationTimestamp,Priority:.spec.priorityClassName,TPU VMs Needed:.spec.podSets[0].count,TPU VMs Running/Ran:.status.admission.podSetAssignments[-1].count,TPU VMs Done:.status.reclaimablePods[0].count,Status:.status.conditions[-1].type,Status Message:.status.conditions[-1].message,Status Time:.status.conditions[-1].lastTransitionTime"  
[XPK] Workload List Output:
0
[XPK] See your workloads in Cloud Console: https://console.cloud.google.com/kubernetes/aiml/deployments/jobs?project=bar
[XPK] Exiting XPK cleanly
-->

## 4. Complex bash expressions work
We can execute command and assign it to a variable.

```shell #golden
XPK_VERSION=$(xpk version)
```
<!--
$ XPK_VERSION=$(xpk version)
-->

Then read it as follows:
```shell #golden
echo "$XPK_VERSION"
```
<!--
$ echo "$XPK_VERSION"
[XPK] Starting xpk v0.0.0
[XPK] xpk_version: v0.0.0
[XPK] XPK Done.
-->
