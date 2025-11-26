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
 
## Storage
Currently XPK supports the below types of storages:
- [Cloud Storage FUSE](#fuse)
- [Google Cloud Filestore](#filestore)
- [Google Cloud Parallelstore](#parallelstore)
- [Google Cloud Block storages (Persistent Disk, Hyperdisk)](#block-storage-persistent-disk-hyperdisk)
- [Google Cloud Managed Lustre](#managed-lustre)

### FUSE
A FUSE adapter lets you mount and access Cloud Storage buckets as local file systems, so workloads can read and write objects in your bucket using standard file system semantics.

To use the GCS FUSE with XPK you need to create a [Storage Bucket](https://console.cloud.google.com/storage/).

Once it's ready you can use `xpk storage attach` with `--type=gcsfuse` command to attach a FUSE storage instance to your cluster:

```shell
xpk storage attach test-fuse-storage --type=gcsfuse \
  --project=$PROJECT --cluster=$CLUSTER --zone=$ZONE 
  --mount-point='/test-mount-point' --readonly=false \
  --bucket=test-bucket --size=1 --auto-mount=false
```

Parameters:

- `--type` - type of the storage, currently xpk supports `gcsfuse` and `gcpfilestore` only.
- `--auto-mount` - if set to true all workloads will have this storage mounted by default.
- `--mount-point` - the path on which this storage should be mounted for a workload.
- `--readonly` - if set to true, workload can only read from storage.
- `--size` - size of the storage in Gb.
- `--bucket` - name of the storage bucket. If not set then the name of the storage is used as a bucket name.
- `--mount-options` - comma-separated list of additional mount options for PersistentVolume ([reference](https://cloud.google.com/kubernetes-engine/docs/how-to/cloud-storage-fuse-csi-driver-perf#mount-options)).
- `--prefetch-metadata` - enables metadata pre-population when mounting the volume by setting parameter `gcsfuseMetadataPrefetchOnMount` to `true` ([reference](https://cloud.google.com/kubernetes-engine/docs/how-to/cloud-storage-fuse-csi-driver-perf#metadata-prefetch)).
- `--manifest` - path to the manifest file containing PersistentVolume and PresistentVolumeClaim definitions. If set, then values from manifest override the following parameters: `--size` and `--bucket`.

### Filestore

A Filestore adapter lets you mount and access [Filestore instances](https://cloud.google.com/filestore/) as local file systems, so workloads can read and write files in your volumes using standard file system semantics.

To create and attach a GCP Filestore instance to your cluster use `xpk storage create` command with `--type=gcpfilestore`:

```shell
xpk storage create test-fs-storage --type=gcpfilestore \
  --auto-mount=false --mount-point=/data-fs --readonly=false \
  --size=1024 --tier=BASIC_HDD --access_mode=ReadWriteMany --vol=default \
  --project=$PROJECT --cluster=$CLUSTER --zone=$ZONE
```

You can also attach an existing Filestore instance to your cluster using `xpk storage attach` command:

```shell
xpk storage attach test-fs-storage --type=gcpfilestore \
  --auto-mount=false --mount-point=/data-fs --readonly=false \
  --size=1024 --tier=BASIC_HDD --access_mode=ReadWriteMany --vol=default \
  --project=$PROJECT --cluster=$CLUSTER --zone=$ZONE
```

The command above is also useful when attaching multiple volumes from the same Filestore instance.

Commands `xpk storage create` and `xpk storage attach` with `--type=gcpfilestore` accept following arguments:
- `--type` - type of the storage.
- `--auto-mount` - if set to true all workloads will have this storage mounted by default.
- `--mount-point` - the path on which this storage should be mounted for a workload.
- `--readonly` - if set to true, workload can only read from storage.
- `--size` - size of the Filestore instance that will be created in Gb.
- `--tier` - tier of the Filestore instance that will be created. Possible options are: `[BASIC_HDD, BASIC_SSD, ZONAL, REGIONAL, ENTERPRISE]`
- `--access-mode` - access mode of the Filestore instance that will be created. Possible values are: `[ReadWriteOnce, ReadOnlyMany, ReadWriteMany]`
- `--vol` - file share name of the Filestore instance that will be created.
- `--instance` - the name of the Filestore instance. If not set then the name parameter is used as an instance name. Useful when connecting multiple volumes from the same Filestore instance.
- `--manifest` - path to the manifest file containing PersistentVolume, PresistentVolumeClaim and StorageClass definitions. If set, then values from manifest override the following parameters: `--access-mode`, `--size` and `--volume`.

### Parallelstore

A Parallelstore adapter lets you mount and access [Parallelstore instances](https://cloud.google.com/parallelstore/) as local file systems, so workloads can read and write files in your volumes using standard file system semantics.

To use the GCS Parallelstore with XPK you need to create a [Parallelstore Instance](https://console.cloud.google.com/parallelstore/).

Once it's ready you can use `xpk storage attach` with `--type=parallelstore` command to attach a Parallelstore instance to your cluster. Currently, attaching a Parallelstore is supported only by providing a manifest file.

```shell
xpk storage attach test-parallelstore-storage --type=parallelstore \
  --project=$PROJECT --cluster=$CLUSTER --zone=$ZONE \
  --mount-point='/test-mount-point' --readonly=false \
  --auto-mount=true \
  --manifest='./examples/storage/parallelstore-manifest-attach.yaml'
```

Parameters:

- `--type` - type of the storage `parallelstore`
- `--auto-mount` - if set to true all workloads will have this storage mounted by default.
- `--mount-point` - the path on which this storage should be mounted for a workload.
- `--readonly` - if set to true, workload can only read from storage.
- `--manifest` - path to the manifest file containing PersistentVolume and PresistentVolumeClaim definitions.

### Block storage (Persistent Disk, Hyperdisk)

A PersistentDisk adapter lets you mount and access Google Cloud Block storage solutions ([Persistent Disk](https://cloud.google.com/kubernetes-engine/docs/concepts/storage-overview#pd), [Hyperdisk](https://cloud.google.com/kubernetes-engine/docs/concepts/storage-overview#hyperdisk)) as local file systems, so workloads can read and write files in your volumes using standard file system semantics.

To use the GCE PersistentDisk with XPK you need to create a [disk in GCE](https://cloud.google.com/compute/docs/disks). Please consider that the disk type you are creating is [compatible with the VMs](https://cloud.google.com/compute/docs/machine-resource#machine_type_comparison) in the default and accelerator nodepools.

Once it's ready you can use `xpk storage attach` with `--type=pd` command to attach a PersistentDisk instance to your cluster. Currently, attaching a PersistentDisk is supported only by providing a manifest file.

```shell
xpk storage attach test-pd-storage --type=pd \
  --project=$PROJECT --cluster=$CLUSTER --zone=$ZONE \
  --mount-point='/test-mount-point' --readonly=false \
  --auto-mount=true \
  --manifest='./examples/storage/pd-manifest-attach.yaml'
```

Parameters:

- `--type` - type of the storage `pd`
- `--auto-mount` - if set to true all workloads will have this storage mounted by default.
- `--mount-point` - the path on which this storage should be mounted for a workload.
- `--readonly` - if set to true, workload can only read from storage.
- `--manifest` - path to the manifest file containing PersistentVolume and PresistentVolumeClaim definitions.

### Managed Lustre

A Managed Lustre adaptor lets you mount and access [Google Cloud Managed Lustre instances](https://cloud.google.com/managed-lustre) as local file systems, so workloads can read and write files in your volumes using standard file system semantics.

To use the GCP Managed Lustre with XPK you need to create [an instance](https://cloud.google.com/managed-lustre/docs/create-instance).

> **Important Note:** 
> Starting from GKE version 1.33.2-gke.4780000, it is no longer necessary to enable GKE support when creating the instance
> (gcloud ex. `--gke-support-enabled`). For more information, check the latest
> [documentation](https://docs.cloud.google.com/managed-lustre/docs/lustre-csi-driver-new-volume#lustre_communication_ports).

Once it's ready you can use `xpk storage attach` with `--type=lustre` command to attach a Managed Lustre instance to your cluster. Currently, attaching a Managed Lustre instance is supported only by providing a manifest file.

```shell
xpk storage attach test-lustre-storage --type=lustre \
  --project=$PROJECT --cluster=$CLUSTER --zone=$ZONE \
  --mount-point='/test-mount-point' --readonly=false \
  --auto-mount=true \
  --manifest='./examples/storage/lustre-manifest-attach.yaml'
```

> **Important Note:** 
> If you are trying to attach to the Lustre instance created with the `--gke-support-enabled` flag, or if your cluster
> is running GKE version earlier than 1.33.2-gke.4780000, you need to add the `--enable-legacy-lustre-port` flag to make
> sure legacy port will be used to connect to the instance. For more information, check the latest
> [documentation](https://docs.cloud.google.com/managed-lustre/docs/lustre-csi-driver-new-volume#lustre_communication_ports).

Parameters:

- `--type` - type of the storage `lustre`
- `--auto-mount` - if set to true all workloads will have this storage mounted by default.
- `--mount-point` - the path on which this storage should be mounted for a workload.
- `--readonly` - if set to true, workload can only read from storage.
- `--manifest` - path to the manifest file containing PersistentVolume and PresistentVolumeClaim definitions.

### List attached storages

```shell
xpk storage list \
  --project=$PROJECT --cluster $CLUSTER --zone=$ZONE
```

### Running workloads with storage

If you specified `--auto-mount=true` when creating or attaching a storage, then all workloads deployed on the cluster will have the volume attached by default. Otherwise, in order to have the storage attached, you have to add `--storage` parameter to `workload create` command:

```shell
xpk workload create \
  --workload xpk-test-workload --command "echo goodbye" \
  --project=$PROJECT --cluster=$CLUSTER --zone=$ZONE \
  --tpu-type=v5litepod-16 --storage=test-storage
```

### Detaching storage

```shell
xpk storage detach $STORAGE_NAME \
  --project=$PROJECT --cluster=$CLUSTER --zone=$ZONE
```

### Deleting storage

XPK allows you to remove Filestore instances easily with `xpk storage delete` command. **Warning:** this deletes all data contained in the Filestore!

```shell
xpk storage delete test-fs-instance \
  --project=$PROJECT --cluster=$CLUSTER --zone=$ZONE
```
