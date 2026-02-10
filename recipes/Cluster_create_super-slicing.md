# Cluster create super-slicing

Creates a GKE cluster with TPU super-slicing enabled for multi-slice training.

# Running the command

```shell #golden
DRY_RUN_RESERVATION_SUB_BLOCKS="name,count,inUseCount:sub0,16,0:sub1,16,0:sub2,16,15:sub3,16,0" xpk cluster create --project=golden-project --zone=us-central1-a --cluster=golden-cluster --tpu-type=tpu7x-4x4x4 --reservation=golden-reservation/reservationBlocks/block --super-slicing --num-cubes=3
```
<!--
$ DRY_RUN_RESERVATION_SUB_BLOCKS="name,count,inUseCount:sub0,16,0:sub1,16,0:sub2,16,15:sub3,16,0" xpk cluster create --project=golden-project --zone=us-central1-a --cluster=golden-cluster --tpu-type=tpu7x-4x4x4 --reservation=golden-reservation/reservationBlocks/block --super-slicing --num-cubes=3
[XPK] Starting xpk v0.0.0
[XPK] Starting cluster create for cluster golden-cluster:
[XPK] Working on golden-project and us-central1-a
[XPK] Task: `Get reservation deployment type` is implemented by the following command not running since it is a dry run. 
gcloud beta compute reservations describe golden-reservation --project=golden-project --zone=us-central1-a --format="value(deploymentType)"
[XPK] Task: `Describe reservation` is implemented by the following command not running since it is a dry run. 
gcloud beta compute reservations describe golden-reservation --project=golden-project --zone=us-central1-a
[XPK] Task: `Determine server supported GKE versions for default gke version` is implemented by the following command not running since it is a dry run. 
gcloud container get-server-config --project=golden-project --region=us-central1 --flatten="channels" --filter="channels.channel=RAPID" --format="value(channels.defaultVersion)"
[XPK] Task: `Determine server supported GKE versions for valid versions` is implemented by the following command not running since it is a dry run. 
gcloud container get-server-config --project=golden-project --region=us-central1 --flatten="channels" --filter="channels.channel=RAPID" --format="value(channels.validVersions)"
[XPK] Task: `Find if Cluster Exists` is implemented by the following command not running since it is a dry run. 
gcloud container clusters list --project=golden-project --filter=location~"us-central1.*" --format="csv[no-heading](name)"
[XPK] Task: `GKE Cluster Create` is implemented by the following command not running since it is a dry run. 
gcloud beta container clusters create golden-cluster --project=golden-project --region=us-central1 --node-locations=us-central1-a --cluster-version=0 --machine-type=e2-standard-16 --enable-autoscaling --total-min-nodes 1 --total-max-nodes 1000 --num-nodes 6 --enable-dns-access --autoscaling-profile=optimize-utilization --labels=gke_product_type=xpk --release-channel=rapid --enable-ip-alias --enable-dataplane-v2 --enable-multi-networking --location-policy=BALANCED --scopes=storage-full,gke-default --enable-slice-controller
[XPK] Task: `Find cluster region or zone` is implemented by the following command not running since it is a dry run. 
gcloud container clusters list --project=golden-project --filter=name=golden-cluster --format="value(location)"
[XPK] Task: `Check if Private Nodes is enabled in cluster.` is implemented by the following command not running since it is a dry run. 
gcloud container clusters describe golden-cluster --project=golden-project --location=us-central1 --format="value(privateClusterConfig.enablePrivateNodes)"
[XPK] Private Nodes is not enabled on the cluster.
[XPK] Cluster is public and no need to authorize networks.
[XPK] Task: `get-credentials-dns-endpoint to cluster golden-cluster` is implemented by the following command not running since it is a dry run. 
gcloud container clusters get-credentials golden-cluster --location=us-central1 --dns-endpoint --project=golden-project && kubectl config view && kubectl config set-context --current --namespace=default
[XPK] Task: `Test kubectl credentials` is implemented by the following command not running since it is a dry run. 
kubectl get pods
[XPK] Finished get-credentials and kubectl setup.
[XPK] Task: 'Checking CoreDNS deployment existence' in progress for namespace: kube-system
[XPK] Task: `Check CoreDNS deployment in kube-system` is implemented by the following command not running since it is a dry run. 
kubectl get deployment coredns -n kube-system
[XPK] Now verifying CoreDNS readiness...
[XPK] Task: `Waiting for kubeDNS to be checked.` is implemented by the following command not running since it is a dry run. 
kubectl get deployment kube-dns -n kube-system --ignore-not-found
[XPK] kube-dns deployment not found.
[XPK] Verifying if CoreDNS is available...
[XPK] Task: `Wait for coredns available` is implemented by the following command not running since it is a dry run. 
kubectl wait deployment/coredns --for=condition=Available=true --namespace=kube-system --timeout=240s
[XPK] CoreDNS has successfully started and passed verification.
[XPK] CoreDNS deployment 'coredns' found in namespace 'kube-system'.
[XPK] Skipping CoreDNS deployment since it already exists.
[XPK] Task: `Determine current gke master version` is implemented by the following command not running since it is a dry run. 
gcloud beta container clusters describe golden-cluster --location us-central1 --project golden-project --format="value(currentMasterVersion)"
[XPK] Creating 3 node pool or pools of tpu7x-4x4x4
We assume that the underlying system is: SystemCharacteristics(topology='4x4x4', vms_per_slice=16, gke_accelerator='tpu7x', gce_machine_type='tpu7x-standard-4t', chips_per_vm=4, accelerator_type=TPU, device_type='tpu7x-128', supports_sub_slicing=False, supports_super_slicing=True, supports_accelerator_network_profile=False, docker_platform=<DockerPlatform.AMD: 'linux/amd64'>, requires_workload_policy=True, gpu_config=None, parallel_containers=2)
[XPK] Task: `Get All Node Pools` is implemented by the following command not running since it is a dry run. 
gcloud beta container node-pools list --cluster golden-cluster --project=golden-project --location=us-central1 --format="csv[no-heading](name)"
[XPK] Task: `Describe reservation` is implemented by the following command not running since it is a dry run. 
gcloud beta compute reservations describe golden-reservation --project=golden-project --zone=us-central1-a
[XPK] Creating 3 node pool or pools of tpu7x-128
Underlyingly, we assume that means: SystemCharacteristics(topology='4x4x4', vms_per_slice=16, gke_accelerator='tpu7x', gce_machine_type='tpu7x-standard-4t', chips_per_vm=4, accelerator_type=TPU, device_type='tpu7x-128', supports_sub_slicing=False, supports_super_slicing=True, supports_accelerator_network_profile=False, docker_platform=<DockerPlatform.AMD: 'linux/amd64'>, requires_workload_policy=True, gpu_config=None, parallel_containers=2)
[XPK] Task: `Get Node Pool Zone` is implemented by the following command not running since it is a dry run. 
gcloud beta container node-pools describe 0 --cluster golden-cluster --project=golden-project --location=us-central1 --format="value(locations)"
[XPK] Task: `GKE Cluster Get ConfigMap` is implemented by the following command not running since it is a dry run. 
kubectl get configmap golden-cluster-resources-configmap -o=custom-columns="ConfigData:data" --no-headers=true
[XPK] Existing node pool names  ['0']
[XPK] Task: `Retrieve resource policy` is implemented by the following command not running since it is a dry run. 
gcloud beta compute resource-policies describe tpu7x-128-4x4x4-ss-placement-policy --project=golden-project --region=us-central1
[XPK] Task: `Count healthy fitting sub-blocks in block` is implemented by the following command not running since it is a dry run. 
gcloud beta compute reservations sub-blocks list golden-reservation --block-name=block --project=golden-project --zone=us-central1-a --filter="healthInfo.healthStatus=HEALTHY" --format="csv(name,count,in_use_count)"
Traceback (most recent call last):
  File "/usr/local/google/home/dominikrabij/xpk-fork/bin/xpk", line 7, in <module>
    sys.exit(main())
             ~~~~^^
  File "/usr/local/google/home/dominikrabij/xpk-fork/src/xpk/main.py", line 93, in main
    main_args.func(main_args)
    ~~~~~~~~~~~~~~^^^^^^^^^^^
  File "/usr/local/google/home/dominikrabij/xpk-fork/src/xpk/commands/cluster.py", line 407, in cluster_create
    run_gke_node_pool_create_command_code = run_gke_node_pool_create_command(
        args, system, gke_node_pool_version
    )
  File "/usr/local/google/home/dominikrabij/xpk-fork/src/xpk/core/nodepool.py", line 281, in run_gke_node_pool_create_command
    reservations_iter, return_code = _prepare_reservation_iterator(
                                     ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~^
        reservations=reservations,
        ^^^^^^^^^^^^^^^^^^^^^^^^^^
    ...<6 lines>...
        ),
        ^^
    )
    ^
  File "/usr/local/google/home/dominikrabij/xpk-fork/src/xpk/core/nodepool.py", line 732, in _prepare_reservation_iterator
    available_capacity, return_code = assess_available_slices(
                                      ~~~~~~~~~~~~~~~~~~~~~~~^
        reservations,
        ^^^^^^^^^^^^^
        force_sub_block_targeting=force_sub_block_targeting,
        ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
        required_hosts=required_hosts,
        ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    )
    ^
  File "/usr/local/google/home/dominikrabij/xpk-fork/src/xpk/core/capacity.py", line 420, in assess_available_slices
    capacities, return_code = _assess_available_slices_for_reservation(
                              ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~^
        reservation, force_sub_block_targeting, required_hosts
        ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    )
    ^
  File "/usr/local/google/home/dominikrabij/xpk-fork/src/xpk/core/capacity.py", line 465, in _assess_available_slices_for_reservation
    return _get_healthy_and_fitting_sub_blocks_in_block(
        reservation, required_hosts
    )
  File "/usr/local/google/home/dominikrabij/xpk-fork/src/xpk/core/capacity.py", line 587, in _get_healthy_and_fitting_sub_blocks_in_block
    in_use_count = int(row['in_use_count'])
                       ~~~^^^^^^^^^^^^^^^^
KeyError: 'in_use_count'
-->
