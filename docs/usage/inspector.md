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
 
## Inspector
* Inspector provides debug info to understand cluster health, and why workloads are not running.
Inspector output is saved to a file.

    ```shell
    xpk inspector \
      --cluster $CLUSTER_NAME \
      --project $PROJECT_ID \
      --zone $ZONE
    ```

* Optional Arguments
  * `--print-to-terminal`:
    Print command output to terminal as well as a file.
  * `--workload $WORKLOAD_NAME`
    Inspector will write debug info related to the workload:`$WORKLOAD_NAME`

* Example Output:

  The output of xpk inspector is in `/tmp/tmp0pd6_k1o` in this example.
  ```shell
  [XPK] Starting xpk
  [XPK] Task: `Set Cluster` succeeded.
  [XPK] Task: `Local Setup: gcloud version` is implemented by `gcloud version`, hiding output unless there is an error.
  [XPK] Task: `Local Setup: Project / Zone / Region` is implemented by `gcloud config get project; gcloud config get compute/zone; gcloud config get compute/region`, hiding output unless there is an error.
  [XPK] Task: `GKE: Cluster Details` is implemented by `gcloud beta container clusters list --project $PROJECT --region $REGION | grep -e NAME -e $CLUSTER_NAME`, hiding output unless there is an error.
  [XPK] Task: `GKE: Node pool Details` is implemented by `gcloud beta container node-pools list --cluster $CLUSTER_NAME  --project=$PROJECT --region=$REGION`, hiding output unless there is an error.
  [XPK] Task: `Kubectl: All Nodes` is implemented by `kubectl get node -o custom-columns='NODE_NAME:metadata.name, READY_STATUS:.status.conditions[?(@.type=="Ready")].status, NODEPOOL:metadata.labels.cloud.google.com/gke-nodepool'`, hiding output unless there is an error.
  [XPK] Task: `Kubectl: Number of Nodes per Node Pool` is implemented by `kubectl get node -o custom-columns=':metadata.labels.cloud.google.com/gke-nodepool' | sort | uniq -c`, hiding output unless there is an error.
  [XPK] Task: `Kubectl: Healthy Node Count Per Node Pool` is implemented by `kubectl get node -o custom-columns='NODE_NAME:metadata.name, READY_STATUS:.status.conditions[?(@.type=="Ready")].status, NODEPOOL:metadata.labels.cloud.google.com/gke-nodepool' | grep -w True | awk {'print $3'} | sort | uniq -c`, hiding output unless there is an error.
  [XPK] Task: `Kueue: ClusterQueue Details` is implemented by `kubectl describe ClusterQueue cluster-queue`, hiding output unless there is an error.
  [XPK] Task: `Kueue: LocalQueue Details` is implemented by `kubectl describe LocalQueue multislice-queue`, hiding output unless there is an error.
  [XPK] Task: `Kueue: Kueue Deployment Details` is implemented by `kubectl describe Deployment kueue-controller-manager -n kueue-system`, hiding output unless there is an error.
  [XPK] Task: `Jobset: Deployment Details` is implemented by `kubectl describe Deployment jobset-controller-manager -n jobset-system`, hiding output unless there is an error.
  [XPK] Task: `Kueue Manager Logs` is implemented by `kubectl logs deployment/kueue-controller-manager -n kueue-system --tail=100 --prefix=True`, hiding output unless there is an error.
  [XPK] Task: `Jobset Manager Logs` is implemented by `kubectl logs deployment/jobset-controller-manager -n jobset-system --tail=100 --prefix=True`, hiding output unless there is an error.
  [XPK] Task: `List Jobs with filter-by-status=EVERYTHING with filter-by-jobs=None` is implemented by `kubectl get workloads -o=custom-columns="Jobset Name:.metadata.ownerReferences[0].name,Created Time:.metadata.creationTimestamp,Priority:.spec.priorityClassName,TPU VMs Needed:.spec.podSets[0].count,TPU VMs Running/Ran:.status.admission.podSetAssignments[-1].count,TPU VMs Done:.status.reclaimablePods[0].count,Status:.status.conditions[-1].type,Status Message:.status.conditions[-1].message,Status Time:.status.conditions[-1].lastTransitionTime"  `, hiding output unless there is an error.
  [XPK] Task: `List Jobs with filter-by-status=QUEUED with filter-by-jobs=None` is implemented by `kubectl get workloads -o=custom-columns="Jobset Name:.metadata.ownerReferences[0].name,Created Time:.metadata.creationTimestamp,Priority:.spec.priorityClassName,TPU VMs Needed:.spec.podSets[0].count,TPU VMs Running/Ran:.status.admission.podSetAssignments[-1].count,TPU VMs Done:.status.reclaimablePods[0].count,Status:.status.conditions[-1].type,Status Message:.status.conditions[-1].message,Status Time:.status.conditions[-1].lastTransitionTime"  | awk -e 'NR == 1 || ($7 ~ "Admitted|Evicted|QuotaReserved" && ($5 ~ "<none>" || $5 == 0)) {print $0}' `, hiding output unless there is an error.
  [XPK] Task: `List Jobs with filter-by-status=RUNNING with filter-by-jobs=None` is implemented by `kubectl get workloads -o=custom-columns="Jobset Name:.metadata.ownerReferences[0].name,Created Time:.metadata.creationTimestamp,Priority:.spec.priorityClassName,TPU VMs Needed:.spec.podSets[0].count,TPU VMs Running/Ran:.status.admission.podSetAssignments[-1].count,TPU VMs Done:.status.reclaimablePods[0].count,Status:.status.conditions[-1].type,Status Message:.status.conditions[-1].message,Status Time:.status.conditions[-1].lastTransitionTime"  | awk -e 'NR == 1 || ($7 ~ "Admitted|Evicted" && $5 ~ /^[0-9]+$/ && $5 > 0) {print $0}' `, hiding output unless there is an error.
  [XPK] Find xpk inspector output file: /tmp/tmp0pd6_k1o
  [XPK] Exiting XPK cleanly
  ```
