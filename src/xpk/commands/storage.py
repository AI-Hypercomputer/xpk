"""
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
"""

from argparse import Namespace

from kubernetes import client as k8s_client
from kubernetes.client.rest import ApiException

from ..core.cluster import (
    setup_k8s_env,
    update_cluster_with_gcsfuse_driver_if_necessary,
    update_cluster_with_workload_identity_if_necessary,
    update_cluster_with_gcpfilestore_driver_if_necessary,
    add_zone_and_project,
    get_cluster_network,
)
from ..core.storage import (
    GCS_FUSE_TYPE,
    GCP_FILESTORE_TYPE,
    STORAGE_CRD_KIND,
    XPK_API_GROUP_NAME,
    XPK_API_GROUP_VERSION,
    create_storage_crds,
    get_storage,
    list_storages,
    print_storages_for_cluster,
)
from ..utils.console import xpk_exit, xpk_print
from ..utils.kubectl import apply_kubectl_manifest
from ..utils.file import ensure_directory_exists
from ..core.filestore import FilestoreClient, get_storage_class_name
from ..core import gcsfuse
import os

manifests_path = os.path.abspath("xpkclusters/storage-manifests")


def storage_create(args: Namespace) -> None:
  ensure_directory_exists(manifests_path)
  add_zone_and_project(args)
  if args.type == GCP_FILESTORE_TYPE:
    filestore_client = FilestoreClient(
        args.zone, args.name, args.project, args.tier
    )
    filestore_exists = filestore_client.check_filestore_instance_exists()
    if filestore_exists:
      xpk_print(f"Filestore instance {args.name} already exists.")
      xpk_exit(1)
    filestore_network = get_cluster_network(args)
    xpk_print(
        f"Creating Filestore instance {args.name} in network:"
        f" {filestore_network}"
    )
    filestore_client.create_filestore_instance(
        vol=args.vol, size=args.size, network=filestore_network
    )

    pv_data = filestore_client.create_pv(args.vol, access_mode=args.access_mode)
    pvc_data = filestore_client.create_pvc(access_mode=args.access_mode)
    sc = filestore_client.create_sc(filestore_network, args.project)
    args.manifest = filestore_client.compile_to_manifest_yaml(
        manifests_path, sc, pv_data, pvc_data
    )
    k8s_api_client = setup_k8s_env(args)
    create_storage_crds(k8s_api_client, args)
    return_code = update_cluster_with_workload_identity_if_necessary(args)
    if return_code > 0:
      xpk_exit(return_code)
    return_code = update_cluster_with_gcpfilestore_driver_if_necessary(args)
    if return_code > 0:
      xpk_exit(return_code)
    apply_kubectl_manifest(k8s_api_client, args.manifest)


def storage_attach(args: Namespace) -> None:
  if args.type == GCP_FILESTORE_TYPE and args.manifest is None:
    xpk_print("---manifest is required when attaching gcpfilestore storage.")
    xpk_exit(1)

  if args.type == GCS_FUSE_TYPE and args.manifest is None:
    if args.size is None:
      xpk_print("--size is required when attaching gcsfuse storage.")
      xpk_exit(1)

    if args.bucket is None:
      args.bucket = args.name

    add_zone_and_project(args)
    ensure_directory_exists(manifests_path)
    args.manifest = (
        f"{manifests_path}/{args.project}-{args.zone}-{args.name}-manifest.yaml"
    )
    gcsfuse.manifest(
        args.manifest, name=args.name, bucket=args.bucket, size=args.size
    )

  k8s_api_client = setup_k8s_env(args)
  create_storage_crds(k8s_api_client, args)
  return_code = update_cluster_with_workload_identity_if_necessary(args)
  if return_code > 0:
    xpk_exit(return_code)

  # args.type can have only two values after parsing
  return_code = (
      update_cluster_with_gcsfuse_driver_if_necessary(args)
      if args.type == GCS_FUSE_TYPE
      else update_cluster_with_gcpfilestore_driver_if_necessary(args)
  )
  if return_code > 0:
    xpk_exit(return_code)

  apply_kubectl_manifest(k8s_api_client, args.manifest)


def storage_list(args: Namespace) -> None:
  k8s_api_client = setup_k8s_env(args)
  storages = list_storages(k8s_api_client)
  print_storages_for_cluster(storages)


def delete_resource(api_call, resource_name: str, resource_kind: str) -> None:
  """
  Deletes a Kubernetes resource and handles potential API exceptions.

  Args:
    api_call: The function to call for deleting the resource.
    resource_name: The name of the resource to delete.
    resource_type: The type of the resource (e.g., "Persistent Volume Claim").
  """
  xpk_print(f"Deleting {resource_kind}:{resource_name}")
  try:
    api_call(resource_name)
  except ApiException as e:
    if e.status == 404:
      xpk_print(
          f"{resource_kind}: {resource_name} not found. "
          f"Might be already deleted. Error: {e}"
      )
      return
    else:
      xpk_print(f"Encountered error during {resource_kind} deletion: {e}")
      xpk_exit(1)
  xpk_print(f"Deleted {resource_kind}:{resource_name}")


def storage_delete(args: Namespace) -> None:
  k8s_api_client = setup_k8s_env(args)
  api_instance = k8s_client.CustomObjectsApi(k8s_api_client)
  core_api = k8s_client.CoreV1Api()
  storage_api = k8s_client.StorageV1Api()
  storage = get_storage(k8s_api_client, args.name)
  delete_resource(
      lambda name: core_api.delete_namespaced_persistent_volume_claim(
          name, "default"
      ),
      storage.pvc,
      "Persistent Volume Claim",
  )
  delete_resource(
      core_api.delete_persistent_volume, storage.pv, "Persistent Volume"
  )

  if storage.type == GCP_FILESTORE_TYPE:
    delete_resource(
        storage_api.delete_storage_class,
        get_storage_class_name(args.name),
        "Storage Class",
    )

  delete_resource(
      lambda name: api_instance.delete_cluster_custom_object(
          name=name,
          group=XPK_API_GROUP_NAME,
          version=XPK_API_GROUP_VERSION,
          plural=STORAGE_CRD_KIND.lower() + "s",
      ),
      args.name,
      "Storage",
  )
