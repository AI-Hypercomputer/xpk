# Workload create pathways super-slicing
Submits a Pathways-enabled workload utilizing TPU super-slicing for large-scale distributed training to the cluster.

# Running the command
```shell #golden
DRY_RUN_RESOURCES_CONFIG_MAP="map[tpu7x-128:80]" xpk workload create-pathways --project=golden-project --zone=us-central1-a --cluster=golden-cluster --workload=golden-workload --command "bash hello" --tpu-type=tpu7x-4x4x20 --script-dir=/tmp
```
<!--
$ DRY_RUN_RESOURCES_CONFIG_MAP="map[tpu7x-128:80]" xpk workload create-pathways --project=golden-project --zone=us-central1-a --cluster=golden-cluster --workload=golden-workload --command "bash hello" --tpu-type=tpu7x-4x4x20 --script-dir=/tmp
[XPK] Starting xpk v0.0.0
[XPK] Task: `Check if Workload Already Exists` is implemented by the following command not running since it is a dry run. 
kubectl get workloads -o=custom-columns='Jobset:.metadata.ownerReferences[0].name'
[XPK] Task: `GKE Cluster Get ConfigMap` is implemented by the following command not running since it is a dry run. 
kubectl get configmap golden-cluster-resources-configmap -o=custom-columns="ConfigData:data" --no-headers=true
[XPK] Task: `Get defined topologies` is implemented by the following command not running since it is a dry run. 
kubectl get topology
[XPK] Task: `Get kueue version on server` is implemented by the following command not running since it is a dry run. 
kubectl get deployment kueue-controller-manager -n kueue-system -o jsonpath='{.spec.template.spec.containers[0].image}'
[XPK] Starting workload create
[XPK] Task: `GKE Cluster Get ConfigMap` is implemented by the following command not running since it is a dry run. 
kubectl get configmap golden-cluster-metadata-configmap -o=custom-columns="ConfigData:data" --no-headers=true
[XPK] Task: `GKE Cluster Get ConfigMap` is implemented by the following command not running since it is a dry run. 
kubectl get configmap golden-cluster-resources-configmap -o=custom-columns="ConfigData:data" --no-headers=true
[XPK] gke_accelerator type not found in config map. Autoprovisioning is not enabled.
[XPK] Workload will be scheduled using the Super-slicing feature.
[XPK] Task: `Find cluster region or zone` is implemented by the following command not running since it is a dry run. 
gcloud container clusters list --project=golden-project --filter=name=golden-cluster --format="value(location)"
[XPK] Task: `Get All Node Pools` is implemented by the following command not running since it is a dry run. 
gcloud beta container node-pools list --cluster golden-cluster --project=golden-project --location=us-central1 --format="csv[no-heading](name)"
[XPK] Temp file (e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855) content: 

[XPK] Adding /tmp to container image archive e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
[XPK] Task: `Upload Container Image` is implemented by the following command not running since it is a dry run. 
crane mutate python:3.10 --append e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 --platform linux/amd64 --tag gcr.io/golden-project/dry-run-runner:prefix-current --workdir /app
[XPK] Deleting container image archive e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
[XPK] Temp file (38cf0ffa4a78684442b5977aa51e2b03f72b35b526c36d5ce9470f72f7a77006) content: 
apiVersion: jobset.x-k8s.io/v1alpha2
kind: JobSet
metadata:
  name: golden-workload
  labels:
    kueue.x-k8s.io/queue-name: multislice-queue  # Name of the LocalQueue
    xpk.google.com/workload: golden-workload
spec:
  coordinator:
    replicatedJob: pathways-head
  network:
    enableDNSHostnames: true
    publishNotReadyAddresses: true
  failurePolicy:
    restartStrategy: Recreate
  replicatedJobs:
  - name: pathways-head
    replicas: 1
    template:
      metadata:
        annotations:
          alpha.jobset.sigs.k8s.io/exclusive-topology: kubernetes.io/hostname
      spec:
        backoffLimit: 0
        completionMode: Indexed
        completions: 1
        parallelism: 1
        template:
          spec:
            hostNetwork: true
            dnsPolicy: ClusterFirstWithHostNet
            nodeSelector:
              cloud.google.com/gke-nodepool: cpu-np
            initContainers:
              - name: pathways-proxy
                image: us-docker.pkg.dev/cloud-tpu-v2-images/pathways/proxy_server:latest
                imagePullPolicy: Always
                args:
                - --server_port=29000
                - --resource_manager_address=$(PATHWAYS_HEAD):29001
                - --gcs_scratch_location=gs://cloud-pathways-staging/tmp
                env:
                - name: PATHWAYS_HEAD
                  valueFrom:
                    fieldRef:
                      fieldPath: metadata.labels['jobset.sigs.k8s.io/coordinator']
                ports:
                - containerPort: 29000
                  protocol: TCP
                resources:
                  limits:
                    cpu: "16"
                    memory: 100G
                restartPolicy: Always
              - name: pathways-rm
                image: us-docker.pkg.dev/cloud-tpu-v2-images/pathways/server:latest
                imagePullPolicy: Always
                args:
                - --server_port=29001
                - --gcs_scratch_location=gs://cloud-pathways-staging/tmp
                - --node_type=resource_manager
                - --instance_count=1
                - --instance_type=tpu7x:4x4x20
                env:
                - name: REPLICATED_JOB_NAME
                  valueFrom:
                    fieldRef:
                      fieldPath: metadata.annotations['jobset.sigs.k8s.io/replicatedjob-name']
                - name: JOBSET_NAME
                  valueFrom:
                    fieldRef:
                      fieldPath: metadata.annotations['jobset.sigs.k8s.io/jobset-name']
                - name: HOST_ADDRESS
                  valueFrom:
                    fieldRef:
                      fieldPath: metadata.labels['jobset.sigs.k8s.io/coordinator']
                - name: TPU_SKIP_MDS_QUERY
                  value: "true"
                ports:
                - containerPort: 29001
                  protocol: TCP
                - containerPort: 29002
                  protocol: TCP
                resources:
                  limits:
                    cpu: "8"
                    memory: 32G
                restartPolicy: Always
            containers:
              - name: jax-tpu
                image: gcr.io/golden-project/dry-run-runner:prefix-current
                imagePullPolicy: Always
                env:
                - name: PATHWAYS_HEAD
                  valueFrom:
                    fieldRef:
                      fieldPath: metadata.labels['jobset.sigs.k8s.io/coordinator']
                - name: JAX_PLATFORMS
                  value: proxy
                - name: XCLOUD_ENVIRONMENT
                  value: GCP
                - name: JAX_BACKEND_TARGET
                  value: grpc://$(PATHWAYS_HEAD):29000 
                securityContext:
                  privileged: true
                command:
                - bash
                - -c
                - |
                  echo XPK Start: $(date);
                  _sigterm() (kill -SIGTERM $! 2>/dev/null;);
                  trap _sigterm SIGTERM;
                  
                  (bash hello) & PID=$!;
                  while kill -0 $PID 2>/dev/null;
                      do sleep 5;
                  done;
                  wait $PID;
                  EXIT_CODE=$?;
                  
                  echo XPK End: $(date);
                  echo EXIT_CODE=$EXIT_CODE;
                  
                  
                  exit $EXIT_CODE
                resources:
                  limits:
                    cpu: "24"
                    memory: 100G

                volumeMounts:
                - mountPath: /tmp
                  name: shared-tmp
                

            restartPolicy: Never
            volumes:
            - hostPath:
                path: /tmp
                type: DirectoryOrCreate
              name: shared-tmp
  - name: worker
    replicas: 1
    template:
      spec:
        backoffLimit: 320
        completionMode: Indexed
        completions: 80
        parallelism: 80
        template:
          metadata:
            labels:
              xpk.google.com/workload: golden-workload
            annotations:
              cloud.google.com/gke-tpu-slice-topology: 4x4x20
          spec:
            hostNetwork: true
            dnsPolicy: ClusterFirstWithHostNet
            terminationGracePeriodSeconds: 30
            priorityClassName: medium
            nodeSelector:
              cloud.google.com/gke-tpu-accelerator: tpu7x
            containers:
              - name: pathways-worker
                image: us-docker.pkg.dev/cloud-tpu-v2-images/pathways/server:latest
                imagePullPolicy: Always
                args:
                - --server_port=29005
                - --resource_manager_address=$(PATHWAYS_HEAD):29001
                - --gcs_scratch_location=gs://cloud-pathways-staging/tmp
                env:
                - name: TPU_MIN_LOG_LEVEL
                  value: "0"
                - name: TF_CPP_MIN_LOG_LEVEL
                  value: "0"
                - name: XCLOUD_ENVIRONMENT
                  value: GCP
                - name: MEGASCALE_GRPC_ENABLE_XOR_TRACER
                  value: "false"
                - name: MEGASCALE_NUM_SLICES
                  valueFrom:
                    fieldRef:
                      fieldPath: metadata.labels['jobset.sigs.k8s.io/replicatedjob-replicas']
                - name: JOBSET_NAME
                  valueFrom:
                    fieldRef:
                      fieldPath: metadata.annotations['jobset.sigs.k8s.io/jobset-name']
                - name: REPLICATED_JOB_NAME
                  valueFrom:
                    fieldRef:
                      fieldPath: metadata.annotations['jobset.sigs.k8s.io/replicatedjob-name']
                - name: MEGASCALE_SLICE_ID
                  valueFrom:
                    fieldRef:
                      fieldPath: metadata.labels['jobset.sigs.k8s.io/job-index']
                - name: PATHWAYS_HEAD
                  valueFrom:
                    fieldRef:
                      fieldPath: metadata.labels['jobset.sigs.k8s.io/coordinator']
                - name: MEGASCALE_COORDINATOR_ADDRESS
                  valueFrom:
                    fieldRef:
                      fieldPath: metadata.labels['jobset.sigs.k8s.io/coordinator']
                ports:
                - containerPort: 29005
                  protocol: TCP
                - containerPort: 29006
                  protocol: TCP
                - containerPort: 8471
                  protocol: TCP
                - containerPort: 8080
                  protocol: TCP
                resources:
                  limits:
                    google.com/tpu: "4"
                volumeMounts:
                - mountPath: /tmp
                  name: shared-tmp
            restartPolicy: OnFailure
            volumes:
            - hostPath:
                path: /tmp
                type: DirectoryOrCreate
              name: shared-tmp
  startupPolicy:
    startupPolicyOrder: InOrder
  successPolicy:
    operator: All
    targetReplicatedJobs:
    - pathways-head
  suspend: false

[XPK] Task: `Creating Workload` is implemented by the following command not running since it is a dry run. 
kubectl apply -f 38cf0ffa4a78684442b5977aa51e2b03f72b35b526c36d5ce9470f72f7a77006
[XPK] Task: `GKE Dashboard List` is implemented by the following command not running since it is a dry run. 
gcloud monitoring dashboards list --project=golden-project --filter="displayName:'GKE - TPU Monitoring Dashboard'" --format="value(name)" --verbosity=error
[XPK] Check statistics and outlier mode of GKE metrics here: https://console.cloud.google.com/monitoring/dashboards/builder/0?project=golden-project&f.rlabel.cluster_name.ClusterName=golden-cluster. To view the metric data for your workload, select golden-workload from the JobName filter on the dashboard.
[XPK] Follow your Pathways workload and other resources here : https://console.cloud.google.com/logs/query;query=resource.type%3D%22k8s_container%22%0Aresource.labels.project_id%3D%22golden-project%22%0Aresource.labels.location%3D%22us-central1%22%0Aresource.labels.cluster_name%3D%22golden-cluster%22%0Aresource.labels.pod_name%3A%22golden-workload-%22%0Aseverity%3E%3DDEFAULT
[XPK] Exiting XPK cleanly
-->

