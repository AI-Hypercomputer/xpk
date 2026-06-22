# Cluster create with adapt_from_ct
Creates a basic GKE cluster, skipping hardware setup via --adapt-from-ct, and setting up only ConfigMaps and Kueue.

# Running the command
```shell #golden
xpk cluster create --project=golden-project --zone=us-central1-a --cluster=golden-cluster --tpu-type=tpu7x-8 --spot --adapt-from-ct
```
<!--
$ xpk cluster create --project=golden-project --zone=us-central1-a --cluster=golden-cluster --tpu-type=tpu7x-8 --spot --adapt-from-ct
[XPK] Starting xpk v0.0.0
[XPK] Starting cluster create for cluster golden-cluster:
[XPK] Working on golden-project and us-central1-a
[XPK] Cluster creation and Nodepool creation was skipped due to the --adapt-from-ct flag.
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

[XPK] Temp file (c7780918e7a1e57b41944f4873efa5e4114a0b59cec19aecd76950f42c98c442) content: 
kind: ConfigMap
apiVersion: v1
metadata:
  name: golden-cluster-metadata-configmap
data:
  xpk_version: v0.0.0
  capacity_type: SPOT

[XPK] Breaking up a total of 2 commands into 1 batches
[XPK] Pretending all the jobs succeeded
[XPK] Enabling the jobset API on our cluster, to be deprecated when Jobset is globally available
[XPK] Try 1: Install Jobset on golden-cluster
[XPK] Task: `Install Jobset on golden-cluster` is implemented by the following command not running since it is a dry run. 
kubectl apply --server-side --force-conflicts -f https://github.com/kubernetes-sigs/jobset/releases/download/v0.10.1/manifests.yaml
[XPK] Task: `Count total nodes` is implemented by the following command not running since it is a dry run. 
kubectl get node --no-headers | wc -l
[XPK] Temp file (fb759a89efb564fb58820d525e144d44a9f158ea19afe084a5ff80e40be78691) content: 

apiVersion: apps/v1
kind: Deployment
metadata:
  labels:
    app.kubernetes.io/component: manager
    app.kubernetes.io/created-by: jobset
    app.kubernetes.io/instance: controller-manager
    app.kubernetes.io/managed-by: kustomize
    app.kubernetes.io/name: deployment
    app.kubernetes.io/part-of: jobset
    control-plane: controller-manager
  name: jobset-controller-manager
  namespace: jobset-system
spec:
  replicas: 1
  selector:
    matchLabels:
      control-plane: controller-manager
  template:
    metadata:
      annotations:
        kubectl.kubernetes.io/default-container: manager
      labels:
        control-plane: controller-manager
    spec:
      containers:
      - args:
        - --config=/controller_manager_config.yaml
        - --zap-log-level=2
        command:
        - /manager
        image: registry.k8s.io/jobset/jobset:v0.10.1
        livenessProbe:
          httpGet:
            path: /healthz
            port: 8081
          initialDelaySeconds: 15
          periodSeconds: 20
        name: manager
        ports:
        - containerPort: 9443
          name: webhook-server
          protocol: TCP
        readinessProbe:
          httpGet:
            path: /readyz
            port: 8081
          initialDelaySeconds: 5
          periodSeconds: 10
        resources:
          limits:
            memory: 4096Mi
          requests:
            cpu: 1000m
            memory: 128Mi
        securityContext:
          allowPrivilegeEscalation: false
          capabilities:
            drop:
            - ALL
        volumeMounts:
        - mountPath: /controller_manager_config.yaml
          name: manager-config
          subPath: controller_manager_config.yaml
        - mountPath: /tmp/k8s-webhook-server/serving-certs
          name: cert
          readOnly: true
      securityContext:
        runAsNonRoot: true
      serviceAccountName: jobset-controller-manager
      terminationGracePeriodSeconds: 10
      volumes:
      - configMap:
          name: jobset-manager-config
        name: manager-config
      - name: cert
        secret:
          defaultMode: 420
          secretName: jobset-webhook-server-cert

[XPK] Try 1: Updating jobset Controller Manager resources
[XPK] Task: `Updating jobset Controller Manager resources` is implemented by the following command not running since it is a dry run. 
kubectl apply -f fb759a89efb564fb58820d525e144d44a9f158ea19afe084a5ff80e40be78691
[XPK] Enabling Kueue on the cluster
[XPK] Task: `Get kueue version on server` is implemented by the following command not running since it is a dry run. 
kubectl get deployment kueue-controller-manager -n kueue-system -o jsonpath='{.spec.template.spec.containers[0].image}'
[XPK] Installing Kueue version v0.17.1...
[XPK] Try 1: Install Kueue
[XPK] Task: `Install Kueue` is implemented by the following command not running since it is a dry run. 
kubectl apply --server-side --force-conflicts -f https://github.com/kubernetes-sigs/kueue/releases/download/v0.17.1/manifests.yaml
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
[XPK] Try 1: Updating Controller Manager resources
[XPK] Task: `Updating Controller Manager resources` is implemented by the following command not running since it is a dry run. 
kubectl patch deployment kueue-controller-manager -n kueue-system --type='strategic' --patch='{"spec": {"template": {"spec": {"containers": [{"name": "manager", "resources": {"requests": {"cpu": "2", "memory": "4096Mi"}, "limits": {"cpu": "2", "memory": "4096Mi"}}}]}}}}'
[XPK] GKE commands done! Resources are created.
[XPK] See your GKE Cluster here: https://console.cloud.google.com/kubernetes/clusters/details/us-central1/golden-cluster/details?project=golden-project
[XPK] Exiting XPK cleanly
-->
