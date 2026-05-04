# Workload create with team-based quota routing

Submits a workload that's auto-routed to a team's per-namespace Kueue
LocalQueue and PriorityClass via the cluster's team-quota ConfigMap. Uses
`XPK_TEAM_QUOTA_DRY_RUN_CONFIG` (mirroring `DRY_RUN_RESERVATION_SUB_BLOCKS`)
so the team-routing path can be exercised without a live cluster — the
recipe shows the rendered JobSet with the correct namespace, priorityClass,
and Kueue/team labels.

# Running the command
```shell #golden
XPK_TEAM_QUOTA_DRY_RUN_CONFIG='{"teams":{"ml-perf":{"namespace":"poc-ml-perf","localQueue":"lq","priorityClass":"poc-ml-perf-priority"},"dev":{"namespace":"poc-dev","localQueue":"lq","priorityClass":"poc-dev-priority"}},"valueClasses":["benchmark","regression","development"],"sliceName":{"charLimit":49,"fixedOverhead":26}}' xpk workload create --project=golden-project --zone=us-central1-a --cluster=golden-cluster --workload=golden-workload --tpu-type=tpu7x-4x4x4 --command="python3 train.py" --team=ml-perf --value-class=benchmark --declared-duration-minutes=90 --dry-run
```
<!--
$ XPK_TEAM_QUOTA_DRY_RUN_CONFIG='{"teams":{"ml-perf":{"namespace":"poc-ml-perf","localQueue":"lq","priorityClass":"poc-ml-perf-priority"},"dev":{"namespace":"poc-dev","localQueue":"lq","priorityClass":"poc-dev-priority"}},"valueClasses":["benchmark","regression","development"],"sliceName":{"charLimit":49,"fixedOverhead":26}}' xpk workload create --project=golden-project --zone=us-central1-a --cluster=golden-cluster --workload=golden-workload --tpu-type=tpu7x-4x4x4 --command="python3 train.py" --team=ml-perf --value-class=benchmark --declared-duration-minutes=90 --dry-run
[XPK] Starting xpk v0.0.0
[XPK] Task: `Check if Workload Already Exists` is implemented by the following command not running since it is a dry run. 
kubectl get workloads -o=custom-columns='Jobset:.metadata.ownerReferences[0].name'
[XPK] Task: `GKE Cluster Get ConfigMap` is implemented by the following command not running since it is a dry run. 
kubectl get configmap golden-cluster-resources-configmap -o=custom-columns="ConfigData:data" --no-headers=true
[XPK] Skipping workload scheduling validation in dry run.
[XPK] Starting workload create
[XPK] Task: `GKE Cluster Get ConfigMap` is implemented by the following command not running since it is a dry run. 
kubectl get configmap golden-cluster-metadata-configmap -o=custom-columns="ConfigData:data" --no-headers=true
[XPK] Task: `GKE Cluster Get ConfigMap` is implemented by the following command not running since it is a dry run. 
kubectl get configmap golden-cluster-resources-configmap -o=custom-columns="ConfigData:data" --no-headers=true
[XPK] gke_accelerator type not found in config map. Autoprovisioning is not enabled.
[XPK] No gcsfuse Storages to add detected
[XPK] No gcp filestore instances to add detected.
[XPK] No gcp parallelstore instances to add detected.
[XPK] No gce persistent disk instances to add detected.
[XPK] No managed lustre instances to add detected.
[XPK] Task: `Retrieve resource policy` is implemented by the following command not running since it is a dry run. 
gcloud beta compute resource-policies describe tpu7x-128-4x4x4-placement-policy --project=golden-project --region=us-central1
[XPK] Temp file (e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855) content: 

[XPK] Adding /home/sivaibhav_google_com/xpk-fork to container image archive e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
[XPK] Task: `Upload Container Image` is implemented by the following command not running since it is a dry run. 
crane mutate python:3.10 --append e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 --platform linux/amd64 --tag gcr.io/golden-project/dry-run-runner:prefix-current --workdir /app
[XPK] Deleting container image archive e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
[XPK] workload "golden-workload" → K8s JobSet name: "golden-b0b9" (shortened to fit super-slice charLimit; use $XPK_WORKLOAD_NAME in your command for GCS artifact paths; pass --no-shorten-jobset-name to disable)
[XPK] Temp file (05390319d2b36dc6e666a1b9859a9ac643e2c4e188733e01e18605ae9e42d463) content: 
apiVersion: jobset.x-k8s.io/v1alpha2
kind: JobSet
metadata:
  name: golden-b0b9
  namespace: poc-ml-perf
  labels:
    kueue.x-k8s.io/queue-name: lq  # Name of the LocalQueue
    xpk.google.com/workload: golden-workload
    team: ml-perf
    value-class: benchmark
    declared-duration-minutes: "90"
  annotations:
    alpha.jobset.sigs.k8s.io/exclusive-topology: cloud.google.com/gke-nodepool
spec:
  ttlSecondsAfterFinished: 43200
  failurePolicy:
    rules:
      - action: FailJobSet
        onJobFailureReasons:
        - PodFailurePolicy
    maxRestarts: 0
  replicatedJobs:
    - name: slice-job
      replicas: 1
      template:
        spec:
          parallelism: 16    # Equal to the number of VMs per slice (or sub-slice).
          completions: 16    # Same as the above.
          backoffLimit: 0   # When any pod fails, the job is failed
          
          podFailurePolicy:
            rules:
          
            - action: FailJob
              onPodConditions: []
              onExitCodes:
                containerName: jax-tpu-1
                operator: NotIn
                values: [42,127,128,129,130,131,132,133,134,135,136,137,138,139,140,141,142,143,144,145,146,147,148,149,150,151,152,153,154,155,156,157,158,159,160,161,162,163,164,165,166,167,168,169,170,171,172,173,174,175,176,177,178,179,180,181,182,183,184,185,186,187,188,189,190,191,192,193,194,195,196,197,198,199,200,201,202,203,204,205,206,207,208,209,210,211,212,213,214,215,216,217,218,219,220,221,222,223,224,225,226,227,228,229,230,231,232,233,234,235,236,237,238,239,240,241,242,243,244,245,246,247,248,249,250,251,252,253,254,255]
            - action: FailJob
              onPodConditions: []
              onExitCodes:
                containerName: jax-tpu-2
                operator: NotIn
                values: [42,127,128,129,130,131,132,133,134,135,136,137,138,139,140,141,142,143,144,145,146,147,148,149,150,151,152,153,154,155,156,157,158,159,160,161,162,163,164,165,166,167,168,169,170,171,172,173,174,175,176,177,178,179,180,181,182,183,184,185,186,187,188,189,190,191,192,193,194,195,196,197,198,199,200,201,202,203,204,205,206,207,208,209,210,211,212,213,214,215,216,217,218,219,220,221,222,223,224,225,226,227,228,229,230,231,232,233,234,235,236,237,238,239,240,241,242,243,244,245,246,247,248,249,250,251,252,253,254,255]
          template:
            metadata:
              labels:
                xpk.google.com/workload: golden-workload
                declared-duration-minutes: "90"
              annotations:
                
                
                
            spec:
              schedulerName: default-scheduler
              imagePullSecrets:
              - name: None
              restartPolicy: Never
              
              nodeSelector:
                cloud.google.com/gke-tpu-accelerator: tpu7x
                cloud.google.com/gke-tpu-topology: 4x4x4
                cloud.google.com/placement-policy-name: tpu7x-128-4x4x4-placement-policy
                
              priorityClassName: poc-ml-perf-priority
              hostNetwork: true
              dnsPolicy: ClusterFirstWithHostNet
              terminationGracePeriodSeconds: 30
              containers:
              
              - name: jax-tpu-1
                image: gcr.io/golden-project/dry-run-runner:prefix-current
                
                env: 
                securityContext:
                  privileged: true
                command:
                - bash
                - -c
                - |
                  echo XPK Start: $(date);
                  _sigterm() (kill -SIGTERM $! 2>/dev/null;);
                  trap _sigterm SIGTERM;
                  
                  (python3 train.py) & PID=$!;
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
                    google.com/tpu: 2

                volumeMounts:
                - mountPath: /dev/shm
                  name: dshm-2
                

              - name: jax-tpu-2
                image: gcr.io/golden-project/dry-run-runner:prefix-current
                
                env: 
                securityContext:
                  privileged: true
                command:
                - bash
                - -c
                - |
                  echo XPK Start: $(date);
                  _sigterm() (kill -SIGTERM $! 2>/dev/null;);
                  trap _sigterm SIGTERM;
                  
                  (python3 train.py) & PID=$!;
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
                    google.com/tpu: 2

                volumeMounts:
                - mountPath: /dev/shm
                  name: dshm-2
                

              serviceAccountName: 
              tolerations:
              
              - operator: "Exists"
                key: google.com/tpu
        
              volumes:
              - emptyDir:
                  medium: Memory
                name: dshm-2
              

[XPK] Task: `Creating Workload` is implemented by the following command not running since it is a dry run. 
kubectl apply -f 05390319d2b36dc6e666a1b9859a9ac643e2c4e188733e01e18605ae9e42d463
[XPK] Task: `GKE Dashboard List` is implemented by the following command not running since it is a dry run. 
gcloud monitoring dashboards list --project=golden-project --filter="displayName:'GKE - TPU Monitoring Dashboard'" --format="value(name)" --verbosity=error
[XPK] Check statistics and outlier mode of GKE metrics here: https://console.cloud.google.com/monitoring/dashboards/builder/0?project=golden-project&f.rlabel.cluster_name.ClusterName=golden-cluster. To view the metric data for your workload, select golden-workload from the JobName filter on the dashboard.
[XPK] Task: `Find cluster region or zone` is implemented by the following command not running since it is a dry run. 
gcloud container clusters list --project=golden-project --filter=name=golden-cluster --format="value(location)"
[XPK] Follow your workload here: https://console.cloud.google.com/kubernetes/service/us-central1/golden-cluster/poc-ml-perf/golden-b0b9/details?project=golden-project
[XPK] Follow your worker 0, slice 0 logs here: Adjust the pod name ([prefix]-slice-job-[slice_number]-[worker_number]) after clicking the url if you want other worker logs. https://console.cloud.google.com/logs/query;query=resource.type%3D%22k8s_container%22%0Aresource.labels.project_id%3D%22golden-project%22%0Aresource.labels.location%3D%22us-central1%22%0Aresource.labels.cluster_name%3D%22golden-cluster%22%0Aresource.labels.namespace_name%3D%22poc-ml-perf%22%0Aresource.labels.pod_name%3A%22golden-b0b9-slice-job-0-0-%22%0Aseverity%3E%3DDEFAULT;storageScope=project;duration=P1D?project=golden-project
[XPK] Exiting XPK cleanly
-->

# Notes

- **`XPK_TEAM_QUOTA_DRY_RUN_CONFIG`** lets you exercise the team-routing
  path without deploying the cluster-side ConfigMap. It accepts the same
  JSON shape as `data["config.json"]` from the live `team-quota-config`
  ConfigMap. Unset or empty → xpk falls back to live `kubectl get
  configmap -n kueue-system team-quota-config`.

- **`--team` overrides `--priority`.** Priority comes from the team's
  `priorityClass` entry in the ConfigMap.

- **Workload name shortening.** When `--team` is set, the user-facing
  `--workload` is mapped to a deterministic short K8s JobSet name
  (`{prefix}-{4-hex}` from `sha256(workload)`) to fit under the super-
  slice admission controller's `charLimit` budget (default 49 chars
  minus `fixedOverhead` 26 minus `len(namespace)`). The original
  workload name is preserved on the `xpk.google.com/workload` label
  and as `$XPK_WORKLOAD_NAME` in the pod env, so training scripts that
  reference the workload name (e.g. for GCS artifact paths) keep
  working unchanged. Pass `--no-shorten-jobset-name` to disable
  shortening and have submission fail loudly when the user-facing
  name exceeds the budget.
