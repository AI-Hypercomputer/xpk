# Cluster create with shared reservation
Creates a GKE cluster using a shared capacity reservation from another project.

# Running the command
```shell #golden
xpk cluster create --project=golden-project --zone=us-central1-a --cluster=golden-cluster --tpu-type=tpu7x-8 --reservation=projects/reservation-project/reservations/golden-reservation
```
<!--
$ xpk cluster create --project=golden-project --zone=us-central1-a --cluster=golden-cluster --tpu-type=tpu7x-8 --reservation=projects/reservation-project/reservations/golden-reservation
[XPK] Starting xpk v0.0.0
[XPK] Starting cluster create for cluster golden-cluster:
[XPK] Working on golden-project and us-central1-a
[XPK] Task: `Get reservation golden-reservation` is implemented by the following command not running since it is a dry run. 
gcloud beta compute reservations describe golden-reservation --project=reservation-project --zone=us-central1-a --format="json(specificReservation,aggregateReservation,status,deploymentType,resourcePolicies)"
[XPK] Assessing reservation capacity to determine number of slices...
[XPK] Automatically setting --num-slices to 100
[XPK] Task: `Determine server supported GKE versions for default gke version` is implemented by the following command not running since it is a dry run. 
gcloud container get-server-config --project=golden-project --region=us-central1 --flatten="channels" --filter="channels.channel=RAPID" --format="value(channels.defaultVersion)"
[XPK] Task: `Determine server supported GKE versions for valid versions` is implemented by the following command not running since it is a dry run. 
gcloud container get-server-config --project=golden-project --region=us-central1 --flatten="channels" --filter="channels.channel=RAPID" --format="value(channels.validVersions)"
[XPK] Task: `Find if Cluster Exists` is implemented by the following command not running since it is a dry run. 
gcloud container clusters list --project=golden-project --filter=location~"us-central1.*" --format="csv[no-heading](name)"
[XPK] Task: `GKE Cluster Create` is implemented by the following command not running since it is a dry run. 
gcloud beta container clusters create golden-cluster --project=golden-project --region=us-central1 --node-locations=us-central1-a --cluster-version=0 --machine-type=e2-standard-16 --enable-autoscaling --total-min-nodes 1 --total-max-nodes 1000 --num-nodes 6 --enable-dns-access --autoscaling-profile=optimize-utilization --labels=gke_product_type=xpk --release-channel=rapid --enable-ip-alias --enable-dataplane-v2 --enable-multi-networking --location-policy=BALANCED --scopes=storage-full,gke-default
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
[XPK] Creating 100 node pool or pools of tpu7x-8
We assume that the underlying system is: SystemCharacteristics(topology='2x2x1', vms_per_slice=1, gke_accelerator='tpu7x', gce_machine_type='tpu7x-standard-4t', chips_per_vm=4, accelerator_type=TPU, device_type='tpu7x-8', supports_sub_slicing=False, supports_super_slicing=False, supports_accelerator_network_profile=False, docker_platform=<DockerPlatform.AMD: 'linux/amd64'>, requires_workload_policy=False, gpu_config=None, parallel_containers=2, pathways_tpu_version='tpu7x')
[XPK] Task: `Get All Node Pools` is implemented by the following command not running since it is a dry run. 
gcloud beta container node-pools list --cluster golden-cluster --project=golden-project --location=us-central1 --format="csv[no-heading](name)"
[XPK] Creating 100 node pool or pools of tpu7x-8
Underlyingly, we assume that means: SystemCharacteristics(topology='2x2x1', vms_per_slice=1, gke_accelerator='tpu7x', gce_machine_type='tpu7x-standard-4t', chips_per_vm=4, accelerator_type=TPU, device_type='tpu7x-8', supports_sub_slicing=False, supports_super_slicing=False, supports_accelerator_network_profile=False, docker_platform=<DockerPlatform.AMD: 'linux/amd64'>, requires_workload_policy=False, gpu_config=None, parallel_containers=2, pathways_tpu_version='tpu7x')
[XPK] Task: `Get Node Pool Zone` is implemented by the following command not running since it is a dry run. 
gcloud beta container node-pools describe 0 --cluster golden-cluster --project=golden-project --location=us-central1 --format="value(locations)"
[XPK] Task: `GKE Cluster Get ConfigMap` is implemented by the following command not running since it is a dry run. 
kubectl get configmap golden-cluster-resources-configmap -o=custom-columns="ConfigData:data" --no-headers=true
[XPK] Existing node pool names  ['0']
[XPK] To complete NodepoolCreate-golden-cluster-np-0 we are executing gcloud beta container node-pools create golden-cluster-np-0 --location=us-central1 --cluster=golden-cluster --project=golden-project --node-locations=us-central1-a --machine-type=tpu7x-standard-4t --host-maintenance-interval=AS_NEEDED --reservation-affinity=specific --reservation=projects/reservation-project/reservations/golden-reservation --enable-gvnic --node-version=0 --num-nodes=1 --scopes=storage-full,gke-default,"https://www.googleapis.com/auth/cloud-platform" 
[XPK] To complete NodepoolCreate-golden-cluster-np-1 we are executing gcloud beta container node-pools create golden-cluster-np-1 --location=us-central1 --cluster=golden-cluster --project=golden-project --node-locations=us-central1-a --machine-type=tpu7x-standard-4t --host-maintenance-interval=AS_NEEDED --reservation-affinity=specific --reservation=projects/reservation-project/reservations/golden-reservation --enable-gvnic --node-version=0 --num-nodes=1 --scopes=storage-full,gke-default,"https://www.googleapis.com/auth/cloud-platform" 
[XPK] To complete NodepoolCreate-golden-cluster-np-10 we are executing gcloud beta container node-pools create golden-cluster-np-10 --location=us-central1 --cluster=golden-cluster --project=golden-project --node-locations=us-central1-a --machine-type=tpu7x-standard-4t --host-maintenance-interval=AS_NEEDED --reservation-affinity=specific --reservation=projects/reservation-project/reservations/golden-reservation --enable-gvnic --node-version=0 --num-nodes=1 --scopes=storage-full,gke-default,"https://www.googleapis.com/auth/cloud-platform" 
[XPK] To complete NodepoolCreate-golden-cluster-np-11 we are executing gcloud beta container node-pools create golden-cluster-np-11 --location=us-central1 --cluster=golden-cluster --project=golden-project --node-locations=us-central1-a --machine-type=tpu7x-standard-4t --host-maintenance-interval=AS_NEEDED --reservation-affinity=specific --reservation=projects/reservation-project/reservations/golden-reservation --enable-gvnic --node-version=0 --num-nodes=1 --scopes=storage-full,gke-default,"https://www.googleapis.com/auth/cloud-platform" 
[XPK] To complete NodepoolCreate-golden-cluster-np-12 we are executing gcloud beta container node-pools create golden-cluster-np-12 --location=us-central1 --cluster=golden-cluster --project=golden-project --node-locations=us-central1-a --machine-type=tpu7x-standard-4t --host-maintenance-interval=AS_NEEDED --reservation-affinity=specific --reservation=projects/reservation-project/reservations/golden-reservation --enable-gvnic --node-version=0 --num-nodes=1 --scopes=storage-full,gke-default,"https://www.googleapis.com/auth/cloud-platform" 
[XPK] To complete NodepoolCreate-golden-cluster-np-13 we are executing gcloud beta container node-pools create golden-cluster-np-13 --location=us-central1 --cluster=golden-cluster --project=golden-project --node-locations=us-central1-a --machine-type=tpu7x-standard-4t --host-maintenance-interval=AS_NEEDED --reservation-affinity=specific --reservation=projects/reservation-project/reservations/golden-reservation --enable-gvnic --node-version=0 --num-nodes=1 --scopes=storage-full,gke-default,"https://www.googleapis.com/auth/cloud-platform" 
[XPK] To complete NodepoolCreate-golden-cluster-np-14 we are executing gcloud beta container node-pools create golden-cluster-np-14 --location=us-central1 --cluster=golden-cluster --project=golden-project --node-locations=us-central1-a --machine-type=tpu7x-standard-4t --host-maintenance-interval=AS_NEEDED --reservation-affinity=specific --reservation=projects/reservation-project/reservations/golden-reservation --enable-gvnic --node-version=0 --num-nodes=1 --scopes=storage-full,gke-default,"https://www.googleapis.com/auth/cloud-platform" 
[XPK] To complete NodepoolCreate-golden-cluster-np-15 we are executing gcloud beta container node-pools create golden-cluster-np-15 --location=us-central1 --cluster=golden-cluster --project=golden-project --node-locations=us-central1-a --machine-type=tpu7x-standard-4t --host-maintenance-interval=AS_NEEDED --reservation-affinity=specific --reservation=projects/reservation-project/reservations/golden-reservation --enable-gvnic --node-version=0 --num-nodes=1 --scopes=storage-full,gke-default,"https://www.googleapis.com/auth/cloud-platform" 
[XPK] To complete NodepoolCreate-golden-cluster-np-16 we are executing gcloud beta container node-pools create golden-cluster-np-16 --location=us-central1 --cluster=golden-cluster --project=golden-project --node-locations=us-central1-a --machine-type=tpu7x-standard-4t --host-maintenance-interval=AS_NEEDED --reservation-affinity=specific --reservation=projects/reservation-project/reservations/golden-reservation --enable-gvnic --node-version=0 --num-nodes=1 --scopes=storage-full,gke-default,"https://www.googleapis.com/auth/cloud-platform" 
[XPK] To complete NodepoolCreate-golden-cluster-np-17 we are executing gcloud beta container node-pools create golden-cluster-np-17 --location=us-central1 --cluster=golden-cluster --project=golden-project --node-locations=us-central1-a --machine-type=tpu7x-standard-4t --host-maintenance-interval=AS_NEEDED --reservation-affinity=specific --reservation=projects/reservation-project/reservations/golden-reservation --enable-gvnic --node-version=0 --num-nodes=1 --scopes=storage-full,gke-default,"https://www.googleapis.com/auth/cloud-platform" 
[XPK] To complete NodepoolCreate-golden-cluster-np-18 we are executing gcloud beta container node-pools create golden-cluster-np-18 --location=us-central1 --cluster=golden-cluster --project=golden-project --node-locations=us-central1-a --machine-type=tpu7x-standard-4t --host-maintenance-interval=AS_NEEDED --reservation-affinity=specific --reservation=projects/reservation-project/reservations/golden-reservation --enable-gvnic --node-version=0 --num-nodes=1 --scopes=storage-full,gke-default,"https://www.googleapis.com/auth/cloud-platform" 
[XPK] To complete NodepoolCreate-golden-cluster-np-19 we are executing gcloud beta container node-pools create golden-cluster-np-19 --location=us-central1 --cluster=golden-cluster --project=golden-project --node-locations=us-central1-a --machine-type=tpu7x-standard-4t --host-maintenance-interval=AS_NEEDED --reservation-affinity=specific --reservation=projects/reservation-project/reservations/golden-reservation --enable-gvnic --node-version=0 --num-nodes=1 --scopes=storage-full,gke-default,"https://www.googleapis.com/auth/cloud-platform" 
[XPK] To complete NodepoolCreate-golden-cluster-np-2 we are executing gcloud beta container node-pools create golden-cluster-np-2 --location=us-central1 --cluster=golden-cluster --project=golden-project --node-locations=us-central1-a --machine-type=tpu7x-standard-4t --host-maintenance-interval=AS_NEEDED --reservation-affinity=specific --reservation=projects/reservation-project/reservations/golden-reservation --enable-gvnic --node-version=0 --num-nodes=1 --scopes=storage-full,gke-default,"https://www.googleapis.com/auth/cloud-platform" 
[XPK] To complete NodepoolCreate-golden-cluster-np-20 we are executing gcloud beta container node-pools create golden-cluster-np-20 --location=us-central1 --cluster=golden-cluster --project=golden-project --node-locations=us-central1-a --machine-type=tpu7x-standard-4t --host-maintenance-interval=AS_NEEDED --reservation-affinity=specific --reservation=projects/reservation-project/reservations/golden-reservation --enable-gvnic --node-version=0 --num-nodes=1 --scopes=storage-full,gke-default,"https://www.googleapis.com/auth/cloud-platform" 
[XPK] To complete NodepoolCreate-golden-cluster-np-21 we are executing gcloud beta container node-pools create golden-cluster-np-21 --location=us-central1 --cluster=golden-cluster --project=golden-project --node-locations=us-central1-a --machine-type=tpu7x-standard-4t --host-maintenance-interval=AS_NEEDED --reservation-affinity=specific --reservation=projects/reservation-project/reservations/golden-reservation --enable-gvnic --node-version=0 --num-nodes=1 --scopes=storage-full,gke-default,"https://www.googleapis.com/auth/cloud-platform" 
[XPK] To complete NodepoolCreate-golden-cluster-np-22 we are executing gcloud beta container node-pools create golden-cluster-np-22 --location=us-central1 --cluster=golden-cluster --project=golden-project --node-locations=us-central1-a --machine-type=tpu7x-standard-4t --host-maintenance-interval=AS_NEEDED --reservation-affinity=specific --reservation=projects/reservation-project/reservations/golden-reservation --enable-gvnic --node-version=0 --num-nodes=1 --scopes=storage-full,gke-default,"https://www.googleapis.com/auth/cloud-platform" 
[XPK] To complete NodepoolCreate-golden-cluster-np-23 we are executing gcloud beta container node-pools create golden-cluster-np-23 --location=us-central1 --cluster=golden-cluster --project=golden-project --node-locations=us-central1-a --machine-type=tpu7x-standard-4t --host-maintenance-interval=AS_NEEDED --reservation-affinity=specific --reservation=projects/reservation-project/reservations/golden-reservation --enable-gvnic --node-version=0 --num-nodes=1 --scopes=storage-full,gke-default,"https://www.googleapis.com/auth/cloud-platform" 
[XPK] To complete NodepoolCreate-golden-cluster-np-24 we are executing gcloud beta container node-pools create golden-cluster-np-24 --location=us-central1 --cluster=golden-cluster --project=golden-project --node-locations=us-central1-a --machine-type=tpu7x-standard-4t --host-maintenance-interval=AS_NEEDED --reservation-affinity=specific --reservation=projects/reservation-project/reservations/golden-reservation --enable-gvnic --node-version=0 --num-nodes=1 --scopes=storage-full,gke-default,"https://www.googleapis.com/auth/cloud-platform" 
[XPK] To complete NodepoolCreate-golden-cluster-np-25 we are executing gcloud beta container node-pools create golden-cluster-np-25 --location=us-central1 --cluster=golden-cluster --project=golden-project --node-locations=us-central1-a --machine-type=tpu7x-standard-4t --host-maintenance-interval=AS_NEEDED --reservation-affinity=specific --reservation=projects/reservation-project/reservations/golden-reservation --enable-gvnic --node-version=0 --num-nodes=1 --scopes=storage-full,gke-default,"https://www.googleapis.com/auth/cloud-platform" 
[XPK] To complete NodepoolCreate-golden-cluster-np-26 we are executing gcloud beta container node-pools create golden-cluster-np-26 --location=us-central1 --cluster=golden-cluster --project=golden-project --node-locations=us-central1-a --machine-type=tpu7x-standard-4t --host-maintenance-interval=AS_NEEDED --reservation-affinity=specific --reservation=projects/reservation-project/reservations/golden-reservation --enable-gvnic --node-version=0 --num-nodes=1 --scopes=storage-full,gke-default,"https://www.googleapis.com/auth/cloud-platform" 
[XPK] To complete NodepoolCreate-golden-cluster-np-27 we are executing gcloud beta container node-pools create golden-cluster-np-27 --location=us-central1 --cluster=golden-cluster --project=golden-project --node-locations=us-central1-a --machine-type=tpu7x-standard-4t --host-maintenance-interval=AS_NEEDED --reservation-affinity=specific --reservation=projects/reservation-project/reservations/golden-reservation --enable-gvnic --node-version=0 --num-nodes=1 --scopes=storage-full,gke-default,"https://www.googleapis.com/auth/cloud-platform" 
[XPK] To complete NodepoolCreate-golden-cluster-np-28 we are executing gcloud beta container node-pools create golden-cluster-np-28 --location=us-central1 --cluster=golden-cluster --project=golden-project --node-locations=us-central1-a --machine-type=tpu7x-standard-4t --host-maintenance-interval=AS_NEEDED --reservation-affinity=specific --reservation=projects/reservation-project/reservations/golden-reservation --enable-gvnic --node-version=0 --num-nodes=1 --scopes=storage-full,gke-default,"https://www.googleapis.com/auth/cloud-platform" 
[XPK] To complete NodepoolCreate-golden-cluster-np-29 we are executing gcloud beta container node-pools create golden-cluster-np-29 --location=us-central1 --cluster=golden-cluster --project=golden-project --node-locations=us-central1-a --machine-type=tpu7x-standard-4t --host-maintenance-interval=AS_NEEDED --reservation-affinity=specific --reservation=projects/reservation-project/reservations/golden-reservation --enable-gvnic --node-version=0 --num-nodes=1 --scopes=storage-full,gke-default,"https://www.googleapis.com/auth/cloud-platform" 
[XPK] To complete NodepoolCreate-golden-cluster-np-3 we are executing gcloud beta container node-pools create golden-cluster-np-3 --location=us-central1 --cluster=golden-cluster --project=golden-project --node-locations=us-central1-a --machine-type=tpu7x-standard-4t --host-maintenance-interval=AS_NEEDED --reservation-affinity=specific --reservation=projects/reservation-project/reservations/golden-reservation --enable-gvnic --node-version=0 --num-nodes=1 --scopes=storage-full,gke-default,"https://www.googleapis.com/auth/cloud-platform" 
[XPK] To complete NodepoolCreate-golden-cluster-np-30 we are executing gcloud beta container node-pools create golden-cluster-np-30 --location=us-central1 --cluster=golden-cluster --project=golden-project --node-locations=us-central1-a --machine-type=tpu7x-standard-4t --host-maintenance-interval=AS_NEEDED --reservation-affinity=specific --reservation=projects/reservation-project/reservations/golden-reservation --enable-gvnic --node-version=0 --num-nodes=1 --scopes=storage-full,gke-default,"https://www.googleapis.com/auth/cloud-platform" 
[XPK] To complete NodepoolCreate-golden-cluster-np-31 we are executing gcloud beta container node-pools create golden-cluster-np-31 --location=us-central1 --cluster=golden-cluster --project=golden-project --node-locations=us-central1-a --machine-type=tpu7x-standard-4t --host-maintenance-interval=AS_NEEDED --reservation-affinity=specific --reservation=projects/reservation-project/reservations/golden-reservation --enable-gvnic --node-version=0 --num-nodes=1 --scopes=storage-full,gke-default,"https://www.googleapis.com/auth/cloud-platform" 
[XPK] To complete NodepoolCreate-golden-cluster-np-32 we are executing gcloud beta container node-pools create golden-cluster-np-32 --location=us-central1 --cluster=golden-cluster --project=golden-project --node-locations=us-central1-a --machine-type=tpu7x-standard-4t --host-maintenance-interval=AS_NEEDED --reservation-affinity=specific --reservation=projects/reservation-project/reservations/golden-reservation --enable-gvnic --node-version=0 --num-nodes=1 --scopes=storage-full,gke-default,"https://www.googleapis.com/auth/cloud-platform" 
[XPK] To complete NodepoolCreate-golden-cluster-np-33 we are executing gcloud beta container node-pools create golden-cluster-np-33 --location=us-central1 --cluster=golden-cluster --project=golden-project --node-locations=us-central1-a --machine-type=tpu7x-standard-4t --host-maintenance-interval=AS_NEEDED --reservation-affinity=specific --reservation=projects/reservation-project/reservations/golden-reservation --enable-gvnic --node-version=0 --num-nodes=1 --scopes=storage-full,gke-default,"https://www.googleapis.com/auth/cloud-platform" 
[XPK] To complete NodepoolCreate-golden-cluster-np-34 we are executing gcloud beta container node-pools create golden-cluster-np-34 --location=us-central1 --cluster=golden-cluster --project=golden-project --node-locations=us-central1-a --machine-type=tpu7x-standard-4t --host-maintenance-interval=AS_NEEDED --reservation-affinity=specific --reservation=projects/reservation-project/reservations/golden-reservation --enable-gvnic --node-version=0 --num-nodes=1 --scopes=storage-full,gke-default,"https://www.googleapis.com/auth/cloud-platform" 
[XPK] To complete NodepoolCreate-golden-cluster-np-35 we are executing gcloud beta container node-pools create golden-cluster-np-35 --location=us-central1 --cluster=golden-cluster --project=golden-project --node-locations=us-central1-a --machine-type=tpu7x-standard-4t --host-maintenance-interval=AS_NEEDED --reservation-affinity=specific --reservation=projects/reservation-project/reservations/golden-reservation --enable-gvnic --node-version=0 --num-nodes=1 --scopes=storage-full,gke-default,"https://www.googleapis.com/auth/cloud-platform" 
[XPK] To complete NodepoolCreate-golden-cluster-np-36 we are executing gcloud beta container node-pools create golden-cluster-np-36 --location=us-central1 --cluster=golden-cluster --project=golden-project --node-locations=us-central1-a --machine-type=tpu7x-standard-4t --host-maintenance-interval=AS_NEEDED --reservation-affinity=specific --reservation=projects/reservation-project/reservations/golden-reservation --enable-gvnic --node-version=0 --num-nodes=1 --scopes=storage-full,gke-default,"https://www.googleapis.com/auth/cloud-platform" 
[XPK] To complete NodepoolCreate-golden-cluster-np-37 we are executing gcloud beta container node-pools create golden-cluster-np-37 --location=us-central1 --cluster=golden-cluster --project=golden-project --node-locations=us-central1-a --machine-type=tpu7x-standard-4t --host-maintenance-interval=AS_NEEDED --reservation-affinity=specific --reservation=projects/reservation-project/reservations/golden-reservation --enable-gvnic --node-version=0 --num-nodes=1 --scopes=storage-full,gke-default,"https://www.googleapis.com/auth/cloud-platform" 
[XPK] To complete NodepoolCreate-golden-cluster-np-38 we are executing gcloud beta container node-pools create golden-cluster-np-38 --location=us-central1 --cluster=golden-cluster --project=golden-project --node-locations=us-central1-a --machine-type=tpu7x-standard-4t --host-maintenance-interval=AS_NEEDED --reservation-affinity=specific --reservation=projects/reservation-project/reservations/golden-reservation --enable-gvnic --node-version=0 --num-nodes=1 --scopes=storage-full,gke-default,"https://www.googleapis.com/auth/cloud-platform" 
[XPK] To complete NodepoolCreate-golden-cluster-np-39 we are executing gcloud beta container node-pools create golden-cluster-np-39 --location=us-central1 --cluster=golden-cluster --project=golden-project --node-locations=us-central1-a --machine-type=tpu7x-standard-4t --host-maintenance-interval=AS_NEEDED --reservation-affinity=specific --reservation=projects/reservation-project/reservations/golden-reservation --enable-gvnic --node-version=0 --num-nodes=1 --scopes=storage-full,gke-default,"https://www.googleapis.com/auth/cloud-platform" 
[XPK] To complete NodepoolCreate-golden-cluster-np-4 we are executing gcloud beta container node-pools create golden-cluster-np-4 --location=us-central1 --cluster=golden-cluster --project=golden-project --node-locations=us-central1-a --machine-type=tpu7x-standard-4t --host-maintenance-interval=AS_NEEDED --reservation-affinity=specific --reservation=projects/reservation-project/reservations/golden-reservation --enable-gvnic --node-version=0 --num-nodes=1 --scopes=storage-full,gke-default,"https://www.googleapis.com/auth/cloud-platform" 
[XPK] To complete NodepoolCreate-golden-cluster-np-40 we are executing gcloud beta container node-pools create golden-cluster-np-40 --location=us-central1 --cluster=golden-cluster --project=golden-project --node-locations=us-central1-a --machine-type=tpu7x-standard-4t --host-maintenance-interval=AS_NEEDED --reservation-affinity=specific --reservation=projects/reservation-project/reservations/golden-reservation --enable-gvnic --node-version=0 --num-nodes=1 --scopes=storage-full,gke-default,"https://www.googleapis.com/auth/cloud-platform" 
[XPK] To complete NodepoolCreate-golden-cluster-np-41 we are executing gcloud beta container node-pools create golden-cluster-np-41 --location=us-central1 --cluster=golden-cluster --project=golden-project --node-locations=us-central1-a --machine-type=tpu7x-standard-4t --host-maintenance-interval=AS_NEEDED --reservation-affinity=specific --reservation=projects/reservation-project/reservations/golden-reservation --enable-gvnic --node-version=0 --num-nodes=1 --scopes=storage-full,gke-default,"https://www.googleapis.com/auth/cloud-platform" 
[XPK] To complete NodepoolCreate-golden-cluster-np-42 we are executing gcloud beta container node-pools create golden-cluster-np-42 --location=us-central1 --cluster=golden-cluster --project=golden-project --node-locations=us-central1-a --machine-type=tpu7x-standard-4t --host-maintenance-interval=AS_NEEDED --reservation-affinity=specific --reservation=projects/reservation-project/reservations/golden-reservation --enable-gvnic --node-version=0 --num-nodes=1 --scopes=storage-full,gke-default,"https://www.googleapis.com/auth/cloud-platform" 
[XPK] To complete NodepoolCreate-golden-cluster-np-43 we are executing gcloud beta container node-pools create golden-cluster-np-43 --location=us-central1 --cluster=golden-cluster --project=golden-project --node-locations=us-central1-a --machine-type=tpu7x-standard-4t --host-maintenance-interval=AS_NEEDED --reservation-affinity=specific --reservation=projects/reservation-project/reservations/golden-reservation --enable-gvnic --node-version=0 --num-nodes=1 --scopes=storage-full,gke-default,"https://www.googleapis.com/auth/cloud-platform" 
[XPK] To complete NodepoolCreate-golden-cluster-np-44 we are executing gcloud beta container node-pools create golden-cluster-np-44 --location=us-central1 --cluster=golden-cluster --project=golden-project --node-locations=us-central1-a --machine-type=tpu7x-standard-4t --host-maintenance-interval=AS_NEEDED --reservation-affinity=specific --reservation=projects/reservation-project/reservations/golden-reservation --enable-gvnic --node-version=0 --num-nodes=1 --scopes=storage-full,gke-default,"https://www.googleapis.com/auth/cloud-platform" 
[XPK] To complete NodepoolCreate-golden-cluster-np-45 we are executing gcloud beta container node-pools create golden-cluster-np-45 --location=us-central1 --cluster=golden-cluster --project=golden-project --node-locations=us-central1-a --machine-type=tpu7x-standard-4t --host-maintenance-interval=AS_NEEDED --reservation-affinity=specific --reservation=projects/reservation-project/reservations/golden-reservation --enable-gvnic --node-version=0 --num-nodes=1 --scopes=storage-full,gke-default,"https://www.googleapis.com/auth/cloud-platform" 
[XPK] To complete NodepoolCreate-golden-cluster-np-46 we are executing gcloud beta container node-pools create golden-cluster-np-46 --location=us-central1 --cluster=golden-cluster --project=golden-project --node-locations=us-central1-a --machine-type=tpu7x-standard-4t --host-maintenance-interval=AS_NEEDED --reservation-affinity=specific --reservation=projects/reservation-project/reservations/golden-reservation --enable-gvnic --node-version=0 --num-nodes=1 --scopes=storage-full,gke-default,"https://www.googleapis.com/auth/cloud-platform" 
[XPK] To complete NodepoolCreate-golden-cluster-np-47 we are executing gcloud beta container node-pools create golden-cluster-np-47 --location=us-central1 --cluster=golden-cluster --project=golden-project --node-locations=us-central1-a --machine-type=tpu7x-standard-4t --host-maintenance-interval=AS_NEEDED --reservation-affinity=specific --reservation=projects/reservation-project/reservations/golden-reservation --enable-gvnic --node-version=0 --num-nodes=1 --scopes=storage-full,gke-default,"https://www.googleapis.com/auth/cloud-platform" 
[XPK] To complete NodepoolCreate-golden-cluster-np-48 we are executing gcloud beta container node-pools create golden-cluster-np-48 --location=us-central1 --cluster=golden-cluster --project=golden-project --node-locations=us-central1-a --machine-type=tpu7x-standard-4t --host-maintenance-interval=AS_NEEDED --reservation-affinity=specific --reservation=projects/reservation-project/reservations/golden-reservation --enable-gvnic --node-version=0 --num-nodes=1 --scopes=storage-full,gke-default,"https://www.googleapis.com/auth/cloud-platform" 
[XPK] To complete NodepoolCreate-golden-cluster-np-49 we are executing gcloud beta container node-pools create golden-cluster-np-49 --location=us-central1 --cluster=golden-cluster --project=golden-project --node-locations=us-central1-a --machine-type=tpu7x-standard-4t --host-maintenance-interval=AS_NEEDED --reservation-affinity=specific --reservation=projects/reservation-project/reservations/golden-reservation --enable-gvnic --node-version=0 --num-nodes=1 --scopes=storage-full,gke-default,"https://www.googleapis.com/auth/cloud-platform" 
[XPK] To complete NodepoolCreate-golden-cluster-np-5 we are executing gcloud beta container node-pools create golden-cluster-np-5 --location=us-central1 --cluster=golden-cluster --project=golden-project --node-locations=us-central1-a --machine-type=tpu7x-standard-4t --host-maintenance-interval=AS_NEEDED --reservation-affinity=specific --reservation=projects/reservation-project/reservations/golden-reservation --enable-gvnic --node-version=0 --num-nodes=1 --scopes=storage-full,gke-default,"https://www.googleapis.com/auth/cloud-platform" 
[XPK] To complete NodepoolCreate-golden-cluster-np-50 we are executing gcloud beta container node-pools create golden-cluster-np-50 --location=us-central1 --cluster=golden-cluster --project=golden-project --node-locations=us-central1-a --machine-type=tpu7x-standard-4t --host-maintenance-interval=AS_NEEDED --reservation-affinity=specific --reservation=projects/reservation-project/reservations/golden-reservation --enable-gvnic --node-version=0 --num-nodes=1 --scopes=storage-full,gke-default,"https://www.googleapis.com/auth/cloud-platform" 
[XPK] To complete NodepoolCreate-golden-cluster-np-51 we are executing gcloud beta container node-pools create golden-cluster-np-51 --location=us-central1 --cluster=golden-cluster --project=golden-project --node-locations=us-central1-a --machine-type=tpu7x-standard-4t --host-maintenance-interval=AS_NEEDED --reservation-affinity=specific --reservation=projects/reservation-project/reservations/golden-reservation --enable-gvnic --node-version=0 --num-nodes=1 --scopes=storage-full,gke-default,"https://www.googleapis.com/auth/cloud-platform" 
[XPK] To complete NodepoolCreate-golden-cluster-np-52 we are executing gcloud beta container node-pools create golden-cluster-np-52 --location=us-central1 --cluster=golden-cluster --project=golden-project --node-locations=us-central1-a --machine-type=tpu7x-standard-4t --host-maintenance-interval=AS_NEEDED --reservation-affinity=specific --reservation=projects/reservation-project/reservations/golden-reservation --enable-gvnic --node-version=0 --num-nodes=1 --scopes=storage-full,gke-default,"https://www.googleapis.com/auth/cloud-platform" 
[XPK] To complete NodepoolCreate-golden-cluster-np-53 we are executing gcloud beta container node-pools create golden-cluster-np-53 --location=us-central1 --cluster=golden-cluster --project=golden-project --node-locations=us-central1-a --machine-type=tpu7x-standard-4t --host-maintenance-interval=AS_NEEDED --reservation-affinity=specific --reservation=projects/reservation-project/reservations/golden-reservation --enable-gvnic --node-version=0 --num-nodes=1 --scopes=storage-full,gke-default,"https://www.googleapis.com/auth/cloud-platform" 
[XPK] To complete NodepoolCreate-golden-cluster-np-54 we are executing gcloud beta container node-pools create golden-cluster-np-54 --location=us-central1 --cluster=golden-cluster --project=golden-project --node-locations=us-central1-a --machine-type=tpu7x-standard-4t --host-maintenance-interval=AS_NEEDED --reservation-affinity=specific --reservation=projects/reservation-project/reservations/golden-reservation --enable-gvnic --node-version=0 --num-nodes=1 --scopes=storage-full,gke-default,"https://www.googleapis.com/auth/cloud-platform" 
[XPK] To complete NodepoolCreate-golden-cluster-np-55 we are executing gcloud beta container node-pools create golden-cluster-np-55 --location=us-central1 --cluster=golden-cluster --project=golden-project --node-locations=us-central1-a --machine-type=tpu7x-standard-4t --host-maintenance-interval=AS_NEEDED --reservation-affinity=specific --reservation=projects/reservation-project/reservations/golden-reservation --enable-gvnic --node-version=0 --num-nodes=1 --scopes=storage-full,gke-default,"https://www.googleapis.com/auth/cloud-platform" 
[XPK] To complete NodepoolCreate-golden-cluster-np-56 we are executing gcloud beta container node-pools create golden-cluster-np-56 --location=us-central1 --cluster=golden-cluster --project=golden-project --node-locations=us-central1-a --machine-type=tpu7x-standard-4t --host-maintenance-interval=AS_NEEDED --reservation-affinity=specific --reservation=projects/reservation-project/reservations/golden-reservation --enable-gvnic --node-version=0 --num-nodes=1 --scopes=storage-full,gke-default,"https://www.googleapis.com/auth/cloud-platform" 
[XPK] To complete NodepoolCreate-golden-cluster-np-57 we are executing gcloud beta container node-pools create golden-cluster-np-57 --location=us-central1 --cluster=golden-cluster --project=golden-project --node-locations=us-central1-a --machine-type=tpu7x-standard-4t --host-maintenance-interval=AS_NEEDED --reservation-affinity=specific --reservation=projects/reservation-project/reservations/golden-reservation --enable-gvnic --node-version=0 --num-nodes=1 --scopes=storage-full,gke-default,"https://www.googleapis.com/auth/cloud-platform" 
[XPK] To complete NodepoolCreate-golden-cluster-np-58 we are executing gcloud beta container node-pools create golden-cluster-np-58 --location=us-central1 --cluster=golden-cluster --project=golden-project --node-locations=us-central1-a --machine-type=tpu7x-standard-4t --host-maintenance-interval=AS_NEEDED --reservation-affinity=specific --reservation=projects/reservation-project/reservations/golden-reservation --enable-gvnic --node-version=0 --num-nodes=1 --scopes=storage-full,gke-default,"https://www.googleapis.com/auth/cloud-platform" 
[XPK] To complete NodepoolCreate-golden-cluster-np-59 we are executing gcloud beta container node-pools create golden-cluster-np-59 --location=us-central1 --cluster=golden-cluster --project=golden-project --node-locations=us-central1-a --machine-type=tpu7x-standard-4t --host-maintenance-interval=AS_NEEDED --reservation-affinity=specific --reservation=projects/reservation-project/reservations/golden-reservation --enable-gvnic --node-version=0 --num-nodes=1 --scopes=storage-full,gke-default,"https://www.googleapis.com/auth/cloud-platform" 
[XPK] To complete NodepoolCreate-golden-cluster-np-6 we are executing gcloud beta container node-pools create golden-cluster-np-6 --location=us-central1 --cluster=golden-cluster --project=golden-project --node-locations=us-central1-a --machine-type=tpu7x-standard-4t --host-maintenance-interval=AS_NEEDED --reservation-affinity=specific --reservation=projects/reservation-project/reservations/golden-reservation --enable-gvnic --node-version=0 --num-nodes=1 --scopes=storage-full,gke-default,"https://www.googleapis.com/auth/cloud-platform" 
[XPK] To complete NodepoolCreate-golden-cluster-np-60 we are executing gcloud beta container node-pools create golden-cluster-np-60 --location=us-central1 --cluster=golden-cluster --project=golden-project --node-locations=us-central1-a --machine-type=tpu7x-standard-4t --host-maintenance-interval=AS_NEEDED --reservation-affinity=specific --reservation=projects/reservation-project/reservations/golden-reservation --enable-gvnic --node-version=0 --num-nodes=1 --scopes=storage-full,gke-default,"https://www.googleapis.com/auth/cloud-platform" 
[XPK] To complete NodepoolCreate-golden-cluster-np-61 we are executing gcloud beta container node-pools create golden-cluster-np-61 --location=us-central1 --cluster=golden-cluster --project=golden-project --node-locations=us-central1-a --machine-type=tpu7x-standard-4t --host-maintenance-interval=AS_NEEDED --reservation-affinity=specific --reservation=projects/reservation-project/reservations/golden-reservation --enable-gvnic --node-version=0 --num-nodes=1 --scopes=storage-full,gke-default,"https://www.googleapis.com/auth/cloud-platform" 
[XPK] To complete NodepoolCreate-golden-cluster-np-62 we are executing gcloud beta container node-pools create golden-cluster-np-62 --location=us-central1 --cluster=golden-cluster --project=golden-project --node-locations=us-central1-a --machine-type=tpu7x-standard-4t --host-maintenance-interval=AS_NEEDED --reservation-affinity=specific --reservation=projects/reservation-project/reservations/golden-reservation --enable-gvnic --node-version=0 --num-nodes=1 --scopes=storage-full,gke-default,"https://www.googleapis.com/auth/cloud-platform" 
[XPK] To complete NodepoolCreate-golden-cluster-np-63 we are executing gcloud beta container node-pools create golden-cluster-np-63 --location=us-central1 --cluster=golden-cluster --project=golden-project --node-locations=us-central1-a --machine-type=tpu7x-standard-4t --host-maintenance-interval=AS_NEEDED --reservation-affinity=specific --reservation=projects/reservation-project/reservations/golden-reservation --enable-gvnic --node-version=0 --num-nodes=1 --scopes=storage-full,gke-default,"https://www.googleapis.com/auth/cloud-platform" 
[XPK] To complete NodepoolCreate-golden-cluster-np-64 we are executing gcloud beta container node-pools create golden-cluster-np-64 --location=us-central1 --cluster=golden-cluster --project=golden-project --node-locations=us-central1-a --machine-type=tpu7x-standard-4t --host-maintenance-interval=AS_NEEDED --reservation-affinity=specific --reservation=projects/reservation-project/reservations/golden-reservation --enable-gvnic --node-version=0 --num-nodes=1 --scopes=storage-full,gke-default,"https://www.googleapis.com/auth/cloud-platform" 
[XPK] To complete NodepoolCreate-golden-cluster-np-65 we are executing gcloud beta container node-pools create golden-cluster-np-65 --location=us-central1 --cluster=golden-cluster --project=golden-project --node-locations=us-central1-a --machine-type=tpu7x-standard-4t --host-maintenance-interval=AS_NEEDED --reservation-affinity=specific --reservation=projects/reservation-project/reservations/golden-reservation --enable-gvnic --node-version=0 --num-nodes=1 --scopes=storage-full,gke-default,"https://www.googleapis.com/auth/cloud-platform" 
[XPK] To complete NodepoolCreate-golden-cluster-np-66 we are executing gcloud beta container node-pools create golden-cluster-np-66 --location=us-central1 --cluster=golden-cluster --project=golden-project --node-locations=us-central1-a --machine-type=tpu7x-standard-4t --host-maintenance-interval=AS_NEEDED --reservation-affinity=specific --reservation=projects/reservation-project/reservations/golden-reservation --enable-gvnic --node-version=0 --num-nodes=1 --scopes=storage-full,gke-default,"https://www.googleapis.com/auth/cloud-platform" 
[XPK] To complete NodepoolCreate-golden-cluster-np-67 we are executing gcloud beta container node-pools create golden-cluster-np-67 --location=us-central1 --cluster=golden-cluster --project=golden-project --node-locations=us-central1-a --machine-type=tpu7x-standard-4t --host-maintenance-interval=AS_NEEDED --reservation-affinity=specific --reservation=projects/reservation-project/reservations/golden-reservation --enable-gvnic --node-version=0 --num-nodes=1 --scopes=storage-full,gke-default,"https://www.googleapis.com/auth/cloud-platform" 
[XPK] To complete NodepoolCreate-golden-cluster-np-68 we are executing gcloud beta container node-pools create golden-cluster-np-68 --location=us-central1 --cluster=golden-cluster --project=golden-project --node-locations=us-central1-a --machine-type=tpu7x-standard-4t --host-maintenance-interval=AS_NEEDED --reservation-affinity=specific --reservation=projects/reservation-project/reservations/golden-reservation --enable-gvnic --node-version=0 --num-nodes=1 --scopes=storage-full,gke-default,"https://www.googleapis.com/auth/cloud-platform" 
[XPK] To complete NodepoolCreate-golden-cluster-np-69 we are executing gcloud beta container node-pools create golden-cluster-np-69 --location=us-central1 --cluster=golden-cluster --project=golden-project --node-locations=us-central1-a --machine-type=tpu7x-standard-4t --host-maintenance-interval=AS_NEEDED --reservation-affinity=specific --reservation=projects/reservation-project/reservations/golden-reservation --enable-gvnic --node-version=0 --num-nodes=1 --scopes=storage-full,gke-default,"https://www.googleapis.com/auth/cloud-platform" 
[XPK] To complete NodepoolCreate-golden-cluster-np-7 we are executing gcloud beta container node-pools create golden-cluster-np-7 --location=us-central1 --cluster=golden-cluster --project=golden-project --node-locations=us-central1-a --machine-type=tpu7x-standard-4t --host-maintenance-interval=AS_NEEDED --reservation-affinity=specific --reservation=projects/reservation-project/reservations/golden-reservation --enable-gvnic --node-version=0 --num-nodes=1 --scopes=storage-full,gke-default,"https://www.googleapis.com/auth/cloud-platform" 
[XPK] To complete NodepoolCreate-golden-cluster-np-70 we are executing gcloud beta container node-pools create golden-cluster-np-70 --location=us-central1 --cluster=golden-cluster --project=golden-project --node-locations=us-central1-a --machine-type=tpu7x-standard-4t --host-maintenance-interval=AS_NEEDED --reservation-affinity=specific --reservation=projects/reservation-project/reservations/golden-reservation --enable-gvnic --node-version=0 --num-nodes=1 --scopes=storage-full,gke-default,"https://www.googleapis.com/auth/cloud-platform" 
[XPK] To complete NodepoolCreate-golden-cluster-np-71 we are executing gcloud beta container node-pools create golden-cluster-np-71 --location=us-central1 --cluster=golden-cluster --project=golden-project --node-locations=us-central1-a --machine-type=tpu7x-standard-4t --host-maintenance-interval=AS_NEEDED --reservation-affinity=specific --reservation=projects/reservation-project/reservations/golden-reservation --enable-gvnic --node-version=0 --num-nodes=1 --scopes=storage-full,gke-default,"https://www.googleapis.com/auth/cloud-platform" 
[XPK] To complete NodepoolCreate-golden-cluster-np-72 we are executing gcloud beta container node-pools create golden-cluster-np-72 --location=us-central1 --cluster=golden-cluster --project=golden-project --node-locations=us-central1-a --machine-type=tpu7x-standard-4t --host-maintenance-interval=AS_NEEDED --reservation-affinity=specific --reservation=projects/reservation-project/reservations/golden-reservation --enable-gvnic --node-version=0 --num-nodes=1 --scopes=storage-full,gke-default,"https://www.googleapis.com/auth/cloud-platform" 
[XPK] To complete NodepoolCreate-golden-cluster-np-73 we are executing gcloud beta container node-pools create golden-cluster-np-73 --location=us-central1 --cluster=golden-cluster --project=golden-project --node-locations=us-central1-a --machine-type=tpu7x-standard-4t --host-maintenance-interval=AS_NEEDED --reservation-affinity=specific --reservation=projects/reservation-project/reservations/golden-reservation --enable-gvnic --node-version=0 --num-nodes=1 --scopes=storage-full,gke-default,"https://www.googleapis.com/auth/cloud-platform" 
[XPK] To complete NodepoolCreate-golden-cluster-np-74 we are executing gcloud beta container node-pools create golden-cluster-np-74 --location=us-central1 --cluster=golden-cluster --project=golden-project --node-locations=us-central1-a --machine-type=tpu7x-standard-4t --host-maintenance-interval=AS_NEEDED --reservation-affinity=specific --reservation=projects/reservation-project/reservations/golden-reservation --enable-gvnic --node-version=0 --num-nodes=1 --scopes=storage-full,gke-default,"https://www.googleapis.com/auth/cloud-platform" 
[XPK] To complete NodepoolCreate-golden-cluster-np-75 we are executing gcloud beta container node-pools create golden-cluster-np-75 --location=us-central1 --cluster=golden-cluster --project=golden-project --node-locations=us-central1-a --machine-type=tpu7x-standard-4t --host-maintenance-interval=AS_NEEDED --reservation-affinity=specific --reservation=projects/reservation-project/reservations/golden-reservation --enable-gvnic --node-version=0 --num-nodes=1 --scopes=storage-full,gke-default,"https://www.googleapis.com/auth/cloud-platform" 
[XPK] To complete NodepoolCreate-golden-cluster-np-76 we are executing gcloud beta container node-pools create golden-cluster-np-76 --location=us-central1 --cluster=golden-cluster --project=golden-project --node-locations=us-central1-a --machine-type=tpu7x-standard-4t --host-maintenance-interval=AS_NEEDED --reservation-affinity=specific --reservation=projects/reservation-project/reservations/golden-reservation --enable-gvnic --node-version=0 --num-nodes=1 --scopes=storage-full,gke-default,"https://www.googleapis.com/auth/cloud-platform" 
[XPK] To complete NodepoolCreate-golden-cluster-np-77 we are executing gcloud beta container node-pools create golden-cluster-np-77 --location=us-central1 --cluster=golden-cluster --project=golden-project --node-locations=us-central1-a --machine-type=tpu7x-standard-4t --host-maintenance-interval=AS_NEEDED --reservation-affinity=specific --reservation=projects/reservation-project/reservations/golden-reservation --enable-gvnic --node-version=0 --num-nodes=1 --scopes=storage-full,gke-default,"https://www.googleapis.com/auth/cloud-platform" 
[XPK] To complete NodepoolCreate-golden-cluster-np-78 we are executing gcloud beta container node-pools create golden-cluster-np-78 --location=us-central1 --cluster=golden-cluster --project=golden-project --node-locations=us-central1-a --machine-type=tpu7x-standard-4t --host-maintenance-interval=AS_NEEDED --reservation-affinity=specific --reservation=projects/reservation-project/reservations/golden-reservation --enable-gvnic --node-version=0 --num-nodes=1 --scopes=storage-full,gke-default,"https://www.googleapis.com/auth/cloud-platform" 
[XPK] To complete NodepoolCreate-golden-cluster-np-79 we are executing gcloud beta container node-pools create golden-cluster-np-79 --location=us-central1 --cluster=golden-cluster --project=golden-project --node-locations=us-central1-a --machine-type=tpu7x-standard-4t --host-maintenance-interval=AS_NEEDED --reservation-affinity=specific --reservation=projects/reservation-project/reservations/golden-reservation --enable-gvnic --node-version=0 --num-nodes=1 --scopes=storage-full,gke-default,"https://www.googleapis.com/auth/cloud-platform" 
[XPK] To complete NodepoolCreate-golden-cluster-np-8 we are executing gcloud beta container node-pools create golden-cluster-np-8 --location=us-central1 --cluster=golden-cluster --project=golden-project --node-locations=us-central1-a --machine-type=tpu7x-standard-4t --host-maintenance-interval=AS_NEEDED --reservation-affinity=specific --reservation=projects/reservation-project/reservations/golden-reservation --enable-gvnic --node-version=0 --num-nodes=1 --scopes=storage-full,gke-default,"https://www.googleapis.com/auth/cloud-platform" 
[XPK] To complete NodepoolCreate-golden-cluster-np-80 we are executing gcloud beta container node-pools create golden-cluster-np-80 --location=us-central1 --cluster=golden-cluster --project=golden-project --node-locations=us-central1-a --machine-type=tpu7x-standard-4t --host-maintenance-interval=AS_NEEDED --reservation-affinity=specific --reservation=projects/reservation-project/reservations/golden-reservation --enable-gvnic --node-version=0 --num-nodes=1 --scopes=storage-full,gke-default,"https://www.googleapis.com/auth/cloud-platform" 
[XPK] To complete NodepoolCreate-golden-cluster-np-81 we are executing gcloud beta container node-pools create golden-cluster-np-81 --location=us-central1 --cluster=golden-cluster --project=golden-project --node-locations=us-central1-a --machine-type=tpu7x-standard-4t --host-maintenance-interval=AS_NEEDED --reservation-affinity=specific --reservation=projects/reservation-project/reservations/golden-reservation --enable-gvnic --node-version=0 --num-nodes=1 --scopes=storage-full,gke-default,"https://www.googleapis.com/auth/cloud-platform" 
[XPK] To complete NodepoolCreate-golden-cluster-np-82 we are executing gcloud beta container node-pools create golden-cluster-np-82 --location=us-central1 --cluster=golden-cluster --project=golden-project --node-locations=us-central1-a --machine-type=tpu7x-standard-4t --host-maintenance-interval=AS_NEEDED --reservation-affinity=specific --reservation=projects/reservation-project/reservations/golden-reservation --enable-gvnic --node-version=0 --num-nodes=1 --scopes=storage-full,gke-default,"https://www.googleapis.com/auth/cloud-platform" 
[XPK] To complete NodepoolCreate-golden-cluster-np-83 we are executing gcloud beta container node-pools create golden-cluster-np-83 --location=us-central1 --cluster=golden-cluster --project=golden-project --node-locations=us-central1-a --machine-type=tpu7x-standard-4t --host-maintenance-interval=AS_NEEDED --reservation-affinity=specific --reservation=projects/reservation-project/reservations/golden-reservation --enable-gvnic --node-version=0 --num-nodes=1 --scopes=storage-full,gke-default,"https://www.googleapis.com/auth/cloud-platform" 
[XPK] To complete NodepoolCreate-golden-cluster-np-84 we are executing gcloud beta container node-pools create golden-cluster-np-84 --location=us-central1 --cluster=golden-cluster --project=golden-project --node-locations=us-central1-a --machine-type=tpu7x-standard-4t --host-maintenance-interval=AS_NEEDED --reservation-affinity=specific --reservation=projects/reservation-project/reservations/golden-reservation --enable-gvnic --node-version=0 --num-nodes=1 --scopes=storage-full,gke-default,"https://www.googleapis.com/auth/cloud-platform" 
[XPK] To complete NodepoolCreate-golden-cluster-np-85 we are executing gcloud beta container node-pools create golden-cluster-np-85 --location=us-central1 --cluster=golden-cluster --project=golden-project --node-locations=us-central1-a --machine-type=tpu7x-standard-4t --host-maintenance-interval=AS_NEEDED --reservation-affinity=specific --reservation=projects/reservation-project/reservations/golden-reservation --enable-gvnic --node-version=0 --num-nodes=1 --scopes=storage-full,gke-default,"https://www.googleapis.com/auth/cloud-platform" 
[XPK] To complete NodepoolCreate-golden-cluster-np-86 we are executing gcloud beta container node-pools create golden-cluster-np-86 --location=us-central1 --cluster=golden-cluster --project=golden-project --node-locations=us-central1-a --machine-type=tpu7x-standard-4t --host-maintenance-interval=AS_NEEDED --reservation-affinity=specific --reservation=projects/reservation-project/reservations/golden-reservation --enable-gvnic --node-version=0 --num-nodes=1 --scopes=storage-full,gke-default,"https://www.googleapis.com/auth/cloud-platform" 
[XPK] To complete NodepoolCreate-golden-cluster-np-87 we are executing gcloud beta container node-pools create golden-cluster-np-87 --location=us-central1 --cluster=golden-cluster --project=golden-project --node-locations=us-central1-a --machine-type=tpu7x-standard-4t --host-maintenance-interval=AS_NEEDED --reservation-affinity=specific --reservation=projects/reservation-project/reservations/golden-reservation --enable-gvnic --node-version=0 --num-nodes=1 --scopes=storage-full,gke-default,"https://www.googleapis.com/auth/cloud-platform" 
[XPK] To complete NodepoolCreate-golden-cluster-np-88 we are executing gcloud beta container node-pools create golden-cluster-np-88 --location=us-central1 --cluster=golden-cluster --project=golden-project --node-locations=us-central1-a --machine-type=tpu7x-standard-4t --host-maintenance-interval=AS_NEEDED --reservation-affinity=specific --reservation=projects/reservation-project/reservations/golden-reservation --enable-gvnic --node-version=0 --num-nodes=1 --scopes=storage-full,gke-default,"https://www.googleapis.com/auth/cloud-platform" 
[XPK] To complete NodepoolCreate-golden-cluster-np-89 we are executing gcloud beta container node-pools create golden-cluster-np-89 --location=us-central1 --cluster=golden-cluster --project=golden-project --node-locations=us-central1-a --machine-type=tpu7x-standard-4t --host-maintenance-interval=AS_NEEDED --reservation-affinity=specific --reservation=projects/reservation-project/reservations/golden-reservation --enable-gvnic --node-version=0 --num-nodes=1 --scopes=storage-full,gke-default,"https://www.googleapis.com/auth/cloud-platform" 
[XPK] To complete NodepoolCreate-golden-cluster-np-9 we are executing gcloud beta container node-pools create golden-cluster-np-9 --location=us-central1 --cluster=golden-cluster --project=golden-project --node-locations=us-central1-a --machine-type=tpu7x-standard-4t --host-maintenance-interval=AS_NEEDED --reservation-affinity=specific --reservation=projects/reservation-project/reservations/golden-reservation --enable-gvnic --node-version=0 --num-nodes=1 --scopes=storage-full,gke-default,"https://www.googleapis.com/auth/cloud-platform" 
[XPK] To complete NodepoolCreate-golden-cluster-np-90 we are executing gcloud beta container node-pools create golden-cluster-np-90 --location=us-central1 --cluster=golden-cluster --project=golden-project --node-locations=us-central1-a --machine-type=tpu7x-standard-4t --host-maintenance-interval=AS_NEEDED --reservation-affinity=specific --reservation=projects/reservation-project/reservations/golden-reservation --enable-gvnic --node-version=0 --num-nodes=1 --scopes=storage-full,gke-default,"https://www.googleapis.com/auth/cloud-platform" 
[XPK] To complete NodepoolCreate-golden-cluster-np-91 we are executing gcloud beta container node-pools create golden-cluster-np-91 --location=us-central1 --cluster=golden-cluster --project=golden-project --node-locations=us-central1-a --machine-type=tpu7x-standard-4t --host-maintenance-interval=AS_NEEDED --reservation-affinity=specific --reservation=projects/reservation-project/reservations/golden-reservation --enable-gvnic --node-version=0 --num-nodes=1 --scopes=storage-full,gke-default,"https://www.googleapis.com/auth/cloud-platform" 
[XPK] To complete NodepoolCreate-golden-cluster-np-92 we are executing gcloud beta container node-pools create golden-cluster-np-92 --location=us-central1 --cluster=golden-cluster --project=golden-project --node-locations=us-central1-a --machine-type=tpu7x-standard-4t --host-maintenance-interval=AS_NEEDED --reservation-affinity=specific --reservation=projects/reservation-project/reservations/golden-reservation --enable-gvnic --node-version=0 --num-nodes=1 --scopes=storage-full,gke-default,"https://www.googleapis.com/auth/cloud-platform" 
[XPK] To complete NodepoolCreate-golden-cluster-np-93 we are executing gcloud beta container node-pools create golden-cluster-np-93 --location=us-central1 --cluster=golden-cluster --project=golden-project --node-locations=us-central1-a --machine-type=tpu7x-standard-4t --host-maintenance-interval=AS_NEEDED --reservation-affinity=specific --reservation=projects/reservation-project/reservations/golden-reservation --enable-gvnic --node-version=0 --num-nodes=1 --scopes=storage-full,gke-default,"https://www.googleapis.com/auth/cloud-platform" 
[XPK] To complete NodepoolCreate-golden-cluster-np-94 we are executing gcloud beta container node-pools create golden-cluster-np-94 --location=us-central1 --cluster=golden-cluster --project=golden-project --node-locations=us-central1-a --machine-type=tpu7x-standard-4t --host-maintenance-interval=AS_NEEDED --reservation-affinity=specific --reservation=projects/reservation-project/reservations/golden-reservation --enable-gvnic --node-version=0 --num-nodes=1 --scopes=storage-full,gke-default,"https://www.googleapis.com/auth/cloud-platform" 
[XPK] To complete NodepoolCreate-golden-cluster-np-95 we are executing gcloud beta container node-pools create golden-cluster-np-95 --location=us-central1 --cluster=golden-cluster --project=golden-project --node-locations=us-central1-a --machine-type=tpu7x-standard-4t --host-maintenance-interval=AS_NEEDED --reservation-affinity=specific --reservation=projects/reservation-project/reservations/golden-reservation --enable-gvnic --node-version=0 --num-nodes=1 --scopes=storage-full,gke-default,"https://www.googleapis.com/auth/cloud-platform" 
[XPK] To complete NodepoolCreate-golden-cluster-np-96 we are executing gcloud beta container node-pools create golden-cluster-np-96 --location=us-central1 --cluster=golden-cluster --project=golden-project --node-locations=us-central1-a --machine-type=tpu7x-standard-4t --host-maintenance-interval=AS_NEEDED --reservation-affinity=specific --reservation=projects/reservation-project/reservations/golden-reservation --enable-gvnic --node-version=0 --num-nodes=1 --scopes=storage-full,gke-default,"https://www.googleapis.com/auth/cloud-platform" 
[XPK] To complete NodepoolCreate-golden-cluster-np-97 we are executing gcloud beta container node-pools create golden-cluster-np-97 --location=us-central1 --cluster=golden-cluster --project=golden-project --node-locations=us-central1-a --machine-type=tpu7x-standard-4t --host-maintenance-interval=AS_NEEDED --reservation-affinity=specific --reservation=projects/reservation-project/reservations/golden-reservation --enable-gvnic --node-version=0 --num-nodes=1 --scopes=storage-full,gke-default,"https://www.googleapis.com/auth/cloud-platform" 
[XPK] To complete NodepoolCreate-golden-cluster-np-98 we are executing gcloud beta container node-pools create golden-cluster-np-98 --location=us-central1 --cluster=golden-cluster --project=golden-project --node-locations=us-central1-a --machine-type=tpu7x-standard-4t --host-maintenance-interval=AS_NEEDED --reservation-affinity=specific --reservation=projects/reservation-project/reservations/golden-reservation --enable-gvnic --node-version=0 --num-nodes=1 --scopes=storage-full,gke-default,"https://www.googleapis.com/auth/cloud-platform" 
[XPK] To complete NodepoolCreate-golden-cluster-np-99 we are executing gcloud beta container node-pools create golden-cluster-np-99 --location=us-central1 --cluster=golden-cluster --project=golden-project --node-locations=us-central1-a --machine-type=tpu7x-standard-4t --host-maintenance-interval=AS_NEEDED --reservation-affinity=specific --reservation=projects/reservation-project/reservations/golden-reservation --enable-gvnic --node-version=0 --num-nodes=1 --scopes=storage-full,gke-default,"https://www.googleapis.com/auth/cloud-platform" 
[XPK] Breaking up a total of 100 commands into 1 batches
[XPK] Pretending all the jobs succeeded
[XPK] Create or delete node pool request complete.
[XPK] Creating ConfigMap for cluster
[XPK] Temp file (b809392891beb105211a654ad49c235628e75ce6b0153493d54bfde7d406f276) content: 
kind: ConfigMap
apiVersion: v1
metadata:
  name: golden-cluster-resources-configmap
data:
  tpu7x-8: "100"

[XPK] Temp file (1e07554ba48dc90eb0b6b215d8604e02dc0152f8662dd1de87472db102e7d2bf) content: 
kind: ConfigMap
apiVersion: v1
metadata:
  name: golden-cluster-metadata-configmap
data:
  xpk_version: v0.0.0
  capacity_type: RESERVATION
  reservation_id: projects/reservation-project/reservations/golden-reservation

[XPK] Breaking up a total of 2 commands into 1 batches
[XPK] Pretending all the jobs succeeded
[XPK] Enabling the jobset API on our cluster, to be deprecated when Jobset is globally available
[XPK] Try 1: Install Jobset on golden-cluster
[XPK] Task: `Install Jobset on golden-cluster` is implemented by the following command not running since it is a dry run. 
kubectl apply --server-side --force-conflicts -f https://github.com/kubernetes-sigs/jobset/releases/download/v0.8.0/manifests.yaml
[XPK] Task: `Count total nodes` is implemented by the following command not running since it is a dry run. 
kubectl get node --no-headers | wc -l
[XPK] Temp file (1b31e624e490f9c8c4ef4e369f08d3fa467990af5a261e4405bd045265d70e95) content: 

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
        image: registry.k8s.io/jobset/jobset:v0.8.0
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
kubectl apply -f 1b31e624e490f9c8c4ef4e369f08d3fa467990af5a261e4405bd045265d70e95
[XPK] Enabling Kueue on the cluster
[XPK] Task: `Get kueue version on server` is implemented by the following command not running since it is a dry run. 
kubectl get deployment kueue-controller-manager -n kueue-system -o jsonpath='{.spec.template.spec.containers[0].image}'
[XPK] Installing Kueue version v0.15.2...
[XPK] Try 1: Install Kueue
[XPK] Task: `Install Kueue` is implemented by the following command not running since it is a dry run. 
kubectl apply --server-side --force-conflicts -f https://github.com/kubernetes-sigs/kueue/releases/download/v0.15.2/manifests.yaml
[XPK] Task: `Wait for Kueue to be available` is implemented by the following command not running since it is a dry run. 
kubectl wait deploy/kueue-controller-manager -n kueue-system --for=condition=available --timeout=10m
[XPK] Temp file (c635087c064c3a29ad3dfdd1e6068758f52d5e3477cad9d88a45c1f84f596029) content: 

apiVersion: kueue.x-k8s.io/v1beta1
kind: ResourceFlavor
metadata:
  name: "100xtpu7x-8"
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
  resourceGroups: [{'coveredResources': ['google.com/tpu'], 'flavors': [{'name': '100xtpu7x-8', 'resources': [{'name': 'google.com/tpu', 'nominalQuota': 400}]}]}]
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
kubectl apply -f c635087c064c3a29ad3dfdd1e6068758f52d5e3477cad9d88a45c1f84f596029
[XPK] Task: `Count total nodes` is implemented by the following command not running since it is a dry run. 
kubectl get node --no-headers | wc -l
[XPK] Try 1: Updating Controller Manager resources
[XPK] Task: `Updating Controller Manager resources` is implemented by the following command not running since it is a dry run. 
kubectl patch deployment kueue-controller-manager -n kueue-system --type='strategic' --patch='{"spec": {"template": {"spec": {"containers": [{"name": "manager", "resources": {"limits": {"memory": "4096Mi"}}}]}}}}'
[XPK] GKE commands done! Resources are created.
[XPK] See your GKE Cluster here: https://console.cloud.google.com/kubernetes/clusters/details/us-central1/golden-cluster/details?project=golden-project
[XPK] Exiting XPK cleanly
-->
