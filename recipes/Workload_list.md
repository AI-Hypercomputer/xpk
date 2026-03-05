# Workload list
Lists all workloads currently present in the cluster.

# Running the command
```shell #golden
xpk workload list --project=golden-project --zone=us-central1-a --cluster=golden-cluster
```
<!--
$ xpk workload list --project=golden-project --zone=us-central1-a --cluster=golden-cluster
[XPK] Starting xpk v0.0.0
[XPK] Starting workload list
[XPK] Working on golden-project and us-central1-a
[XPK] Task: `Find cluster region or zone` is implemented by the following command not running since it is a dry run. 
gcloud container clusters list --project=golden-project --filter=name=golden-cluster --format="value(location)"
[XPK] Task: `get-credentials-dns-endpoint to cluster golden-cluster` is implemented by the following command not running since it is a dry run. 
gcloud container clusters get-credentials golden-cluster --location=us-central1 --dns-endpoint --project=golden-project && kubectl config view && kubectl config set-context --current --namespace=default
[XPK] Task: `Test kubectl credentials` is implemented by the following command not running since it is a dry run. 
kubectl get pods
[XPK] Finished get-credentials and kubectl setup.
[XPK] Task: `List Jobs with filter-by-status=EVERYTHING` is implemented by the following command not running since it is a dry run. 
kubectl get workloads --ignore-not-found -o=jsonpath='{range .items[*]}JOBSET_NAME={.metadata.ownerReferences[0].name}CREATED_TIME={.metadata.creationTimestamp}PRIORITY={.spec.priorityClassName}TPU_VMS_NEEDED={.spec.podSets[0].count}TPU_VMS_RUNNING_RAN={.status.admission.podSetAssignments[-1].count}TPU_VMS_DONE={.status.reclaimablePods[0].count}STATUS={.status.conditions[-1].type}STATUS_MESSAGE={.status.conditions[-1].message}STATUS_TIME={.status.conditions[-1].lastTransitionTime}{""}{end}'
[XPK] Workload List Output:
Jobset Name   Created Time   Priority   TPU VMs Needed   TPU VMs Running/Ran   TPU VMs Done   Status   Status Message   Status Time
[XPK] See your workloads in Cloud Console: https://console.cloud.google.com/kubernetes/aiml/deployments/jobs?project=golden-project
[XPK] Exiting XPK cleanly
-->
