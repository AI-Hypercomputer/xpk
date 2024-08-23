<!--
 Copyright 2024 Google LLC

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

# Advanced usage - Use a Jupyter notebook to interact with a Cloud TPU cluster

[Return to README](README.md#other-advanced-usage)

## Introduction
One of the challenges researchers face when working with contemporary models is the distributed programming involved to orchestrate work with a complex architecture. This example shows you how to use XPK to create a Cloud TPU v5e-256 cluster and interact with it using a Jupyter notebook.

## Assumptions
You need to ensure you have the TPU capacity (quotas and limits) for this activity.  You may need to change machine names and shapes to make this work.

To interact with the cluster, we use IPython Parallels and some [cell magic](https://ipyparallel.readthedocs.io/en/latest/tutorial/magics.html). IPython Parallels (ipyparallel) is a Python package and collection of CLI scripts for controlling clusters of IPython processes, built on the Jupyter protocol. While the default settings were adequate for this example, you should review [ipyparallel security details](https://ipyparallel.readthedocs.io/en/latest/reference/security.html) before use in a production environment.
We do most of this work from a Cloud Shell instance.  We will use some environment variables to make life easier.
```shell
export PROJECTID=${GOOGLE_CLOUD_PROJECT}
export CLUSTER=  # your cluster name
export REGION=   # region for cluster
export ZONE=     # zone for cluster
```

## Cluster creation
### Optional:  high-MTU network
If you need to work with multiple TPU slices, it will be useful to create a high-MTU network as shown here (the remaining steps assume you do):
https://github.com/google/maxtext/tree/main/MaxText/configs#create-a-custom-mtu-network
```shell
gcloud compute networks create mtu9k --mtu=8896 \
--project=${PROJECTID} --subnet-mode=auto \
--bgp-routing-mode=regional

gcloud compute firewall-rules create mtu9kfw --network mtu9k \
--allow tcp,icmp,udp --project=${PROJECTID}
```

### XPK create cluster
Install XPK.  (You know, this repo!)

Create a GKE Cloud TPU cluster using XPK.
```shell
xpk cluster create --cluster ${CLUSTER} \
--project=${PROJECTID} --default-pool-cpu-machine-type=n2-standard-8 \
--num-slices=1 --tpu-type=v5litepod-256 --zone=${ZONE} \
--spot --custom-cluster-arguments="--network=mtu9k --subnetwork=mtu9k"

# if you need to delete this cluster to fix errors
xpk cluster delete --cluster ${CLUSTER} --zone=${ZONE}
```

## Add storage
Enable filestore plugin so we can use an NFS Filestore instance for shared storage.  (This may take 20-30 minutes.)
```shell
gcloud container clusters update ${CLUSTER} \
--region ${REGION} --project ${PROJECTID} \
--update-addons=GcpFilestoreCsiDriver=ENABLED
```

### Filestore instance
Create a regional NFS [Filestore instance](https://cloud.google.com/filestore/docs/creating-instances#google-cloud-console) in ``${REGION}`` and the named network above.

Note the instance ID and file share name you’ve used.  You will need to wait until this instance is available to continue.


### Persistent volumes
Once the Filestore instance is up, create a file with the correct names and storage size so you can create a persistent volume for the cluster.  You will need to update the volumeHandle and volumeAttributes below.  You will also need to change the names to match.
```yaml
# persistent-volume.yaml
apiVersion: v1
kind: PersistentVolume
metadata:
  name: opmvol
spec:
  storageClassName: ""
  capacity:
    storage: 1Ti
  accessModes:
    - ReadWriteMany
  persistentVolumeReclaimPolicy: Retain
  volumeMode: Filesystem
  csi:
    driver: filestore.csi.storage.gke.io
    volumeHandle: "modeInstance/${ZONE}/nfs-opm-ase/nfs_opm_ase"
    volumeAttributes:
      ip: 10.243.23.194
      volume: nfs_opm_ase
---
kind: PersistentVolumeClaim
apiVersion: v1
metadata:
  name: opmvol-claim
spec:
  accessModes:
    - ReadWriteMany
  storageClassName: ""
  volumeName: opmvol
  resources:
    requests:
      storage: 1T
```

Apply the change.  Be sure to get the cluster credentials first if you haven’t already done that.
```shell
# get cluster credentials if needed
# gcloud container clusters get-credentials ${CLUSTER} --region ${REGION} --project ${PROJECTID}
# kubectl get nodes

# add the storage to the cluster
kubectl apply -f persistent-volume.yaml
```

If it worked, you should see the volume listed.
```shell
kubectl get pv
kubectl get pvc
```

## Build Docker image for IPP nodes
We will start with the MaxText image because we want to train an LLM.
```shell
# get the code
git clone "https://github.com/google/maxtext"
```

We’ll start with a JAX stable image for TPUs and then update the build specification to include ipyparallel.  Edit the ``requirements_with_jax_stable_stack.txt`` to add this at the bottom.
```shell
# also include IPyParallel
ipyparallel
```

Build the image and upload it so we can use the image to spin up pods.  Note the resulting image name.  It should be something like ``gcr.io/${PROJECTID}/opm_ipp_runner/tpu``.
```shell
# use docker build to build the image and upload it
# NOTE:  you may need to change the upload repository
bash ./docker_maxtext_jax_stable_stack_image_upload.sh PROJECT_ID=${PROJECTID} \
  BASEIMAGE=us-docker.pkg.dev/${PROJECTID}/jax-stable-stack/tpu:jax0.4.30-rev1 \
  CLOUD_IMAGE_NAME=opm_ipp_runner IMAGE_TAG=latest \
  MAXTEXT_REQUIREMENTS_FILE=requirements_with_jax_stable_stack.txt

# confirm the image is available
# docker image list gcr.io/${PROJECTID}/opm_ipp_runner/tpu:latest
```

## Set up LWS
We use the LeaderWorkerSet for these IPP pods, so they are managed collectively.
```shell
kubectl apply --server-side -f https://github.com/kubernetes-sigs/lws/releases/download/v0.3.0/manifests.yaml
```

## Set up IPP deployment
Next we set up an LWS pod specification for our IPP instances.  Create an ``ipp-deployment.yaml`` file.
You will need to update the volume mounts and the container image references.  (You should also change the password.)
```yaml
# ipp-deployment.yaml
apiVersion: leaderworkerset.x-k8s.io/v1
kind: LeaderWorkerSet
metadata:
  name: ipp-deployment
  annotations:
    leaderworkerset.sigs.k8s.io/exclusive-topology: cloud.google.com/gke-nodepool
spec:
  replicas: 1
  leaderWorkerTemplate:
    size: 65
    restartPolicy: RecreateGroupOnPodRestart
    leaderTemplate:
      metadata:
        labels:
            app: ipp-controller
      spec:
        securityContext:
          runAsUser: 1000
          runAsGroup: 100
          fsGroup: 100
        nodeSelector:
          cloud.google.com/gke-tpu-topology: 16x16
          cloud.google.com/gke-tpu-accelerator: tpu-v5-lite-podslice
        tolerations:
        - key: "google.com/tpu"
          operator: "Exists"
          effect: "NoSchedule"
        containers:
        - name: jupyter-notebook-server
          image: jupyter/base-notebook:latest
          args: ["start-notebook.sh",  "--NotebookApp.allow_origin='https://colab.research.google.com'", "--NotebookApp.port_retries=0"]
          resources:
            limits:
              cpu: 1000m
              memory: 1Gi
            requests:
              cpu: 100m
              memory: 500Mi
          ports:
          - containerPort: 8888
            name: http-web-svc
          volumeMounts:
          - name: opmvol
            mountPath: /home/jovyan/nfs # jovyan is the default user
        - name: ipp-controller
          image: gcr.io/${PROJECTID}/opm_ipp_runner/tpu
          command:
              - bash
              - -c
              - |
                ip=$(hostname -I | awk '{print $1}')
                echo $ip
                ipcontroller --ip="$ip" --profile-dir=/app/ipp --log-level=ERROR --ping 10000
          volumeMounts:
            - name: opmvol
              mountPath: /app/ipp
        volumes:
            - name: opmvol
              persistentVolumeClaim:
                claimName: opmvol-claim

    workerTemplate:
      spec:
        nodeSelector:
          cloud.google.com/gke-tpu-topology: 16x16
          cloud.google.com/gke-tpu-accelerator: tpu-v5-lite-podslice
        containers:

        - name: ipp-engine
          image: gcr.io/${PROJECTID}/opm_ipp_runner/tpu
          ports:
          - containerPort: 8471 # Default port using which TPU VMs communicate
          securityContext:
            privileged: true
          command:
          - bash
          - -c
          - |
            sleep 20
            ipengine --file="/app/ipp/security/ipcontroller-engine.json" --timeout 5.0
          resources:
            requests:
              google.com/tpu: 4
            limits:
              google.com/tpu: 4
          volumeMounts:
            - name: opmvol
              mountPath: /app/ipp
        volumes:
            - name: opmvol
              persistentVolumeClaim:
                claimName: opmvol-claim
```

Add the resource to the GKE cluster.
```shell
kubectl apply -f ipp-deployment.yaml

# to view pod status as they come up
# kubectl get pods
```
Add a service to expose it.

Create ``ipp-service.yaml``
```yaml
# ipp-service.yaml
apiVersion: v1
kind: Service
metadata:
  name: ipp
spec:
  selector:
    app: ipp-controller
  ports:
  - protocol: TCP
    port: 8888
    targetPort: 8888
  type: ClusterIP #LoadBalancer
```

Deploy the new service.
```shell
kubectl apply -f ipp-service.yaml
```

If the pods don’t come up as a multihost cluster, you may need to correct the number of hosts depending on the number of chips (e.g., a v5e-256 should have an LWS size of 65 (64 ipp-engines and 1 ipp-controller)).  If you need to look at a single container in isolation, you can use something like this.
```shell
# you should NOT have to do this
# kubectl exec ipp-deployment-0-2 -c ipp-engine -- python3 -c "import jax; jax.device_count()"
```

To correct errors, you can re-apply an updated template and re-create the leader pod.
```shell
# to fetch an updated docker image without changing anything else
# kubectl delete pod ipp-deployment-0

# to update the resource definition (automatically re-creates pods)
# kubectl apply -f ipp-deployment.yaml

# to update the resource definition after an immutable change, you will likely need to use Console
# (i.e., delete Workloads lws-controller-manager, ipp, and ipp-deployment)
# and then you'll also need to delete the resource
# kubectl delete leaderworkerset/ipp-deployment
# kubectl delete service/ipp
```

## Optional:  optimize networking
If you did create a high-MTU network, you should use the MaxText [preflight.sh](https://github.com/google/maxtext/blob/main/preflight.sh) script (which invokes another script) to tune the network settings for the pods before using them with the notebook (the MaxText reference training scripts automatically do this).
```shell
for pod in $(kubectl get pods --no-headers --output jsonpath="{range.items[*]}{..metadata.name}{'\n'}{end}" | grep ipp-deployment-0-); \
do \
    echo "${pod}";
    kubectl exec ${pod} -c ipp-engine -- bash ./preflight.sh;
done
```

## Use the notebook
Get the link to the notebook …
```shell
kubectl logs ipp-deployment-0 --container jupyter-notebook-server

# see the line that shows something like this
#http://127.0.0.1:8888/lab?token=1c9012cd239e13b2123028ae26436d2580a7d4fc1d561125
```

Setup local port forwarding to your service so requests from your browser are ultimately routed to your Jupyter service.
```shell
# you will need to do this locally (e.g., laptop), so you probably need to
# gcloud container clusters get-credentials ${CLUSTER} --region ${REGION} --project ${PROJECTID}
kubectl port-forward service/ipp 8888:8888

# Example notebook
# https://gist.github.com/nhira/ea4b93738aadb1111b2ee5868d56a22b
```
