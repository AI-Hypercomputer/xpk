# Cluster delete
Deletes a GKE cluster and cleans up associated resources.

# Running the command
```shell #golden
xpk cluster delete --project=golden-project --zone=us-central1-a --cluster=golden-cluster
```
<!--
$ xpk cluster delete --project=golden-project --zone=us-central1-a --cluster=golden-cluster
[XPK] Starting xpk v0.0.0
[XPK] Starting cluster delete for cluster: golden-cluster
[XPK] Working on golden-project and us-central1-a
[XPK] Task: `Find cluster region or zone` is implemented by the following command not running since it is a dry run. 
gcloud container clusters list --project=golden-project --filter=name=golden-cluster --format="value(location)"
[XPK] Try 1: get-credentials to cluster golden-cluster
[XPK] Task: `get-credentials to cluster golden-cluster` is implemented by the following command not running since it is a dry run. 
gcloud container clusters get-credentials golden-cluster --location=us-central1 --dns-endpoint --project=golden-project && kubectl config view && kubectl config set-context --current --namespace=default
[XPK] Get the name of the workloads in the cluster.
[XPK] Task: `List Jobs with filter-by-status=EVERYTHING` is implemented by the following command not running since it is a dry run. 
kubectl get workloads --ignore-not-found -o=jsonpath='{range .items[*]}JOBSET_NAME={.metadata.ownerReferences[0].name}CREATED_TIME={.metadata.creationTimestamp}PRIORITY={.spec.priorityClassName}TPU_VMS_NEEDED={.spec.podSets[0].count}TPU_VMS_RUNNING_RAN={.status.admission.podSetAssignments[-1].count}TPU_VMS_DONE={.status.reclaimablePods[0].count}STATUS={.status.conditions[-1].type}STATUS_MESSAGE={.status.conditions[-1].message}STATUS_TIME={.status.conditions[-1].lastTransitionTime}{""}{end}'
[XPK] Planning to delete 1 workloads in the cluster golden-cluster including ['<empty>']. 
Do you wish to delete? (y/N): Traceback (most recent call last):
  File "/usr/local/google/home/dominikrabij/xpk-fork/bin/xpk", line 7, in <module>
    sys.exit(main())
             ~~~~^^
  File "/usr/local/google/home/dominikrabij/xpk-fork2/src/xpk/main.py", line 100, in main
    main_args.func(main_args)
    ~~~~~~~~~~~~~~^^^^^^^^^^^
  File "/usr/local/google/home/dominikrabij/xpk-fork2/src/xpk/commands/cluster.py", line 506, in cluster_delete
    run_gke_cluster_delete_command_code = run_gke_cluster_delete_command(args)
  File "/usr/local/google/home/dominikrabij/xpk-fork2/src/xpk/commands/cluster.py", line 1152, in run_gke_cluster_delete_command
    if workloads and not ask_for_user_consent(
                         ~~~~~~~~~~~~~~~~~~~~^
        f'Planning to delete {len(workloads)} workloads in the cluster'
        ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
        f' {args.cluster} including {workloads}. \nDo you wish to delete?'
        ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    ):
    ^
  File "/usr/local/google/home/dominikrabij/xpk-fork2/src/xpk/utils/console.py", line 69, in ask_for_user_consent
    user_input = input(prompt) or default_option
                 ~~~~~^^^^^^^^
EOFError: EOF when reading a line
-->
