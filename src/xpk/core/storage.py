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

import os
from argparse import Namespace
from dataclasses import dataclass
from typing import Any

import ruamel.yaml
from google.cloud import storage as gcp_storage
from kubernetes import client as k8s_client
from kubernetes import utils
from kubernetes.client import ApiClient
from kubernetes.client.models.v1_persistent_volume import V1PersistentVolume
from kubernetes.client.rest import ApiException
from kubernetes.utils import FailToCreateError
from tabulate import tabulate

from ..utils.console import xpk_exit, xpk_print
from ..utils.file import ensure_directory_exists
from ..utils import templates
from .cluster import XPK_SA

yaml = ruamel.yaml.YAML()

STORAGE_CRD_PATH = "/../api/storage_crd.yaml"
STORAGE_TEMPLATE_PATH = "/../templates/storage.yaml"
XPK_API_GROUP_NAME = "xpk.x-k8s.io"
XPK_API_GROUP_VERSION = "v1"
STORAGE_CRD_KIND = "Storage"
STORAGE_CRD_PLURAL = "storages"
STORAGE_CRD_NAME = f"{XPK_API_GROUP_NAME}.{STORAGE_CRD_PLURAL}"
GCS_FUSE_TYPE = "gcsfuse"
GCP_FILESTORE_TYPE = "gcpfilestore"
MANIFESTS_PATH = os.path.abspath("xpkclusters/storage-manifests")
GCS_FUSE_ANNOTATION = 'gke-gcsfuse/volumes: "true"'


@dataclass
class Storage:
  """
  Represents a Storage custom resource in Kubernetes.

  Attributes:
      name: The name of the Storage resource.
      type: The type of storage (e.g., 'GCSFuse').
      cluster: The cluster where the storage is located.
      auto_mount: Whether the storage should be automatically mounted to every workload.
      mount_point: The path on which a given storage should be mounted for a workload.
      readonly: Whether the storage is read-only.
      manifest: The path to a yaml file containing PersistentVolume and PersistentVolumeClaim for a given storage.
      pvc: The name of the PersistentVolumeClaim associated with the storage.
      pv: The name of the PersistentVolume associated with the storage.
      bucket: The name of the GCS Fuse bucket/ GCP Filestore PersistentVolume refers to.
  """

  name: str
  type: str
  auto_mount: bool
  mount_point: str
  readonly: bool
  manifest: str
  pvc: str
  pv: str
  bucket: str

  def __init__(self, data: dict):
    """
    Initializes a Storage object from a dictionary.

    Args:
        data: A dictionary containing the Storage resource definition.
    """
    metadata: k8s_client.V1ObjectMeta = data.get("metadata", {})
    self.name = metadata.get("name")
    spec = data.get("spec", {})
    self.type: str = spec.get("type")
    self.auto_mount: bool = spec.get("auto_mount")
    self.mount_point: bool = spec.get("mount_point")
    self.readonly: bool = spec.get("readonly")
    self.manifest: str = spec.get("manifest")
    self.pvc: str = spec.get("pvc")
    self.pv: str = spec.get("pv")
    self.bucket: str = self._get_bucket()

  def fields_as_list(self) -> list[str]:
    """
    Returns a list of fields for display purposes.

    Returns:
        A list of strings representing the Storage object's fields.
    """
    return [
        self.name,
        self.type,
        self.auto_mount,
        self.mount_point,
        self.readonly,
        self.manifest,
    ]

  def _get_bucket(self) -> str:
    """
    Retrieves the bucket name from PersistentVolume definition associated with the storage.

    Returns:
        The name of the bucket.
    """
    client = k8s_client.CoreV1Api()
    try:
      pv: V1PersistentVolume = client.read_persistent_volume(self.pv)
      return pv.spec.csi.volume_handle
    except ApiException as e:
      xpk_print(
          f"Exception when calling CoreV1Api->read_persistent_volume: {e}"
      )
      return ""

  def get_mount_options(self) -> list[str]:
    """
    Retrieves the mount options for the PersistentVolume.

    Returns:
        A list of mount options.
    """
    client = k8s_client.CoreV1Api()
    try:
      pv: V1PersistentVolume = client.read_persistent_volume(self.pv)
      return pv.spec.mount_options
    except ApiException as e:
      xpk_print(
          f"Exception when calling CoreV1Api->read_persistent_volume: {e}"
      )
      return []


def list_storages(k8s_api_client: ApiClient) -> list[Storage]:
  """
  Lists all Storage custom resources in the cluster.

  Args:
      k8s_api_client: An ApiClient object for interacting with the Kubernetes API.

  Returns:
      A list of Storage objects representing the Storage resources.
  """
  api_instance = k8s_client.CustomObjectsApi(k8s_api_client)
  try:
    resp = api_instance.list_cluster_custom_object(
        group=XPK_API_GROUP_NAME,
        version=XPK_API_GROUP_VERSION,
        plural=STORAGE_CRD_PLURAL,
    )
  except ApiException as e:
    xpk_print(f"Kubernetes API exception while listing Storages: {e}")
    if e.status == 404:
      xpk_print("Storages not found, skipping")
      return []
    # If it's a different error, then we should just exit.
    xpk_exit(1)

  storages = []
  for stg in resp["items"]:
    storage = Storage(stg)
    storages.append(storage)
  return storages


def get_auto_mount_storages(k8s_api_client: ApiClient) -> list[Storage]:
  """
  Retrieves all Storage resources that have --auto-mount flag set to true.

  Args:
      k8s_api_client: An ApiClient object for interacting with the Kubernetes API.

  Returns:
      A list of Storage objects that have `auto_mount` set to True.
  """
  auto_mount_storages: list[Storage] = []
  for storage in list_storages(k8s_api_client):
    if storage.auto_mount is True:
      auto_mount_storages.append(storage)
  return auto_mount_storages


def get_auto_mount_gcsfuse_storages(k8s_api_client: ApiClient) -> list[Storage]:
  """
  Retrieves all GCS Fuse Storage resources that have --auto-mount flag set to true.

  Args:
      k8s_api_client: An ApiClient object for interacting with the Kubernetes API.

  Returns:
      A list of GCS Fuse Storage objects that have `auto_mount` set to True.
  """
  storages: list[Storage] = get_auto_mount_storages(k8s_api_client)
  return list(filter(lambda storage: storage.type == GCS_FUSE_TYPE, storages))


def get_storages(
    k8s_api_client: ApiClient, requested_storages: list[str]
) -> list[Storage]:
  """
  Retrieves a list of Storage resources by their names.

  Args:
      k8s_api_client: An ApiClient object for interacting with the Kubernetes API.
      names: A list of Storage resource names to retrieve.

  Returns:
      A list of Storage objects matching the given names.
  """
  all_storages = list_storages(k8s_api_client)
  all_storage_names = {storage.name for storage in all_storages}

  for storage_name in requested_storages:
    if storage_name not in all_storage_names:
      xpk_print(
          f"Storage: {storage_name} not found. Choose one of the available"
          f" storages: {list(all_storage_names)}"
      )
      xpk_exit(1)

  storages: list[Storage] = list(
      storage for storage in all_storages if storage.name in requested_storages
  )
  return storages


def get_storages_to_mount(
    k8s_api_client: ApiClient, requested_storages: list[str]
) -> list[Storage]:
  """
  Retrieves a list of Storage resources by their names, including auto-mounted storages.

  Args:
      k8s_api_client: An ApiClient object for interacting with the Kubernetes API.
      names: A list of Storage resource names to retrieve.

  Returns:
      A list of Storage objects matching the given names and any auto-mounted storages.
  """
  storages = get_storages(k8s_api_client, requested_storages)
  for auto_mounted_stg in get_auto_mount_storages(k8s_api_client):
    # prevent duplicating storages
    if auto_mounted_stg.name not in requested_storages:
      storages.append(auto_mounted_stg)

  return storages


def get_storage(k8s_api_client: ApiClient, name: str) -> Storage:
  """
  Retrieves a specific Storage custom resource by its name.

  Args:
      k8s_api_client: An ApiClient object for interacting with the Kubernetes API.
      name: The name of the Storage resource to retrieve.

  Returns:
      A Storage object representing the retrieved Storage resource.
  """
  api_instance = k8s_client.CustomObjectsApi(k8s_api_client)
  try:
    resp = api_instance.get_cluster_custom_object(
        name=name,
        group=XPK_API_GROUP_NAME,
        version=XPK_API_GROUP_VERSION,
        plural=STORAGE_CRD_PLURAL,
    )
    return Storage(resp)
  except ApiException as e:
    xpk_print(f"Kubernetes API exception while getting Storage {name}: {e}")
    xpk_exit(1)


def install_storage_crd(k8s_api_client: ApiClient) -> None:
  """
  Installs the Storage custom resource definition (CRD) in the Kubernetes cluster.

  Args:
      k8s_api_client: An ApiClient object for interacting with the Kubernetes API.
  """
  xpk_print(f"Creating a new CRD: {STORAGE_CRD_NAME}")
  try:
    utils.create_from_yaml(
        k8s_api_client,
        f"{os.path.dirname(__file__)}{STORAGE_CRD_PATH}",
        verbose=True,
    )
    xpk_print(f"Created a CRD: {STORAGE_CRD_NAME} successfully")
  except FailToCreateError as e:
    for api_exception in e.api_exceptions:
      if api_exception.status == 409:
        xpk_print(
            f"CRD: {STORAGE_CRD_NAME} already exists. Skipping its creation"
        )
      break
    else:
      xpk_print(f"Encountered error during installing Storage CRD: {e}")
      xpk_exit(1)


def get_storage_volume_mounts_yaml(storages: list[Storage]) -> str:
  """
  Generates the YAML representation of the volumeMounts section for the given Storages.

  This function creates the YAML snippet that defines how the storage volumes
  should be mounted within a Pod's containers.

  Args:
      storages: A list of Storage objects.

  Returns:
      A string containing the YAML representation of the volumeMounts section.
  """
  yaml_str = ""
  for storage in storages:
    yaml_str += f"""- name: {storage.pv}
                  mountPath: {storage.mount_point}
                  readOnly: {storage.readonly}
            """
  return yaml_str


def get_storage_volumes_yaml(storages: list[Storage]) -> str:
  """
  Generates the YAML representation of the volumes section for the given Storages.

  This function creates the YAML snippet that defines the volumes to be
  mounted in a Pod, including the PersistentVolumeClaim associated with
  each Storage.

  Args:
      storages: A list of Storage objects.

  Returns:
      A string containing the YAML representation of the volumes section.
  """
  yaml_str = ""
  for storage in storages:
    yaml_str += f"""- name: {storage.pv}
                persistentVolumeClaim:
                  claimName: {storage.pvc}
                  readOnly: {storage.readonly}
            """
  return yaml_str


def get_storage_volume_mounts_yaml_for_gpu(storages: list[Storage]) -> str:
  """
  Generates the YAML representation of the volumeMounts section for the given Storages.

  This function creates the YAML snippet that defines how the storage volumes
  should be mounted within a Pod's containers.

  Args:
      storages: A list of Storage objects.

  Returns:
      A string containing the YAML representation of the volumeMounts section.
  """
  yaml_str = ""
  for storage in storages:
    yaml_str += f"""- name: {storage.pv}
                  mountPath: {storage.mount_point}
                  readOnly: {storage.readonly}
            """
  return yaml_str


def get_storage_volumes_yaml_for_gpu(storages: list[Storage]) -> str:
  """
  Generates the YAML representation of the volumes section for the given Storages.

  This function creates the YAML snippet that defines the volumes to be
  mounted in a Pod, including the PersistentVolumeClaim associated with
  each Storage.

  Args:
      storages: A list of Storage objects.

  Returns:
      A string containing the YAML representation of the volumes section.
  """
  yaml_str = ""
  for storage in storages:
    yaml_str += f"""- name: {storage.pv}
                persistentVolumeClaim:
                  claimName: {storage.pvc}
                  readOnly: {storage.readonly}
            """
  return yaml_str


def get_storage_volumes_yaml_dict(storages: list[Storage]) -> list[dict]:
  vols = []
  for storage in storages:
    vols.append({
        "name": storage.pv,
        "persistentVolumeClaim": {
            "claimName": storage.pvc,
            "readOnly": storage.readonly,
        },
    })
  return vols


def add_bucket_iam_members(args: Namespace, storages: list[Storage]) -> None:
  """
  Adds IAM members to the GCS buckets associated with the given Storages.

  This function grants the necessary permissions to the XPK service account
  to access the GCS buckets. The specific role (viewer or user) is determined
  based on the `readonly` attribute of each Storage object.

  Args:
      args: An argparse Namespace object containing command-line arguments.
      storages: A list of Storage objects.
  """
  storage_client = gcp_storage.Client()

  for storage in storages:
    if storage.type == GCS_FUSE_TYPE:
      bucket = storage_client.bucket(storage.bucket)
      policy = bucket.get_iam_policy(requested_policy_version=3)
      if storage.readonly:
        role = "roles/storage.objectViewer"
      else:
        role = "roles/storage.objectUser"

      member = (
          f"principal://iam.googleapis.com/projects/{args.project_number}/"
          f"locations/global/workloadIdentityPools/{args.project}.svc.id.goog/"
          f"subject/ns/default/sa/{XPK_SA}"
      )

      policy.bindings.append({"role": role, "members": {member}})
      bucket.set_iam_policy(policy)
      xpk_print(f"Added {member} with role {role} to {storage.bucket}.")


def print_storages_for_cluster(storages: list[Storage]) -> None:
  """
  Prints in human readable manner a table of Storage resources that belong to the specified cluster.

  Args:
      storages: A list of Storage objects.
      cluster: The name of the cluster to filter by.
  """
  headers = [
      "NAME",
      "TYPE",
      "AUTO MOUNT",
      "MOUNT POINT",
      "READONLY",
      "MANIFEST",
  ]
  storage_tab = []
  for storage in storages:
    storage_tab.append(storage.fields_as_list())

  print(
      tabulate(
          storage_tab,
          headers=headers,
      )
  )


def save_manifest(args: Namespace, manifest: list[dict]):
  """
  Saves manifest to file in xpkclusters/storage-manifests.

  Args:
      args: An argparser Namespace object containing arguments for creating the
            Storage resource.
      manifest: A list of some of: PersistentVolume, PersistentVolumeClaim and
                StorageClass definitions

  Returns:
      manifest_path: Manifest file path
  """
  ensure_directory_exists(MANIFESTS_PATH)
  manifest_path = f"{MANIFESTS_PATH}/{args.project}-{args.zone}-{args.cluster}-{args.name}-manifest.yaml"
  with open(manifest_path, "w", encoding="utf-8") as f:
    yaml.dump_all(manifest, f)
  return manifest_path


def save_storage_crds(k8s_api_client: ApiClient, data: Any):
  """
  Saves a new Storage custom resource in the Kubernetes cluster.

  Args:
      k8s_api_client: An ApiClient object for interacting with the Kubernetes API.
      data: A dictionary containing data to save.
  """
  api_instance = k8s_client.CustomObjectsApi(k8s_api_client)

  api_instance.create_cluster_custom_object(
      group=XPK_API_GROUP_NAME,
      version=XPK_API_GROUP_VERSION,
      plural=STORAGE_CRD_PLURAL,
      body=data,
  )
  xpk_print(f"Created {STORAGE_CRD_KIND} object: {data['metadata']['name']}")


def fill_storage_template(
    template: dict, args: Namespace, manifest: list[dict], manifest_path: str
):
  """
  Populates storage.yaml template with data.

  Args:
      template: A storage custom resource definition template
      args: An argparse Namespace object containing the arguments for creating
            the Storage resource.
      manifest: A list of some of: PersistentVolume, PersistentVolumeClaim and
                StorageClass definitions
  """
  template["metadata"]["name"] = args.name
  template["spec"] = {
      "auto_mount": args.auto_mount,
      "cluster": args.cluster,
      "mount_point": args.mount_point,
      "readonly": args.readonly,
      "type": args.type,
      "manifest": manifest_path,
  }

  for obj in manifest:
    if obj["kind"] == "PersistentVolume":
      template["spec"]["pv"] = obj["metadata"]["name"]
    elif obj["kind"] == "PersistentVolumeClaim":
      template["spec"]["pvc"] = obj["metadata"]["name"]


def create_storage_crds(
    k8s_api_client: ApiClient, args: Namespace, manifest: list[dict]
) -> None:
  """
  Creates a new Storage custom resource in the Kubernetes cluster.

  This function reads a Storage template from a YAML file, populates it with
  values from the provided arguments, and then creates the Storage object
  in the cluster.

  Args:
      k8s_api_client: An ApiClient object for interacting with the Kubernetes API.
      args: An argparse Namespace object containing the arguments for creating
            the Storage resource.
      manifest: A list of some of: PersistentVolume, PersistentVolumeClaim and
                StorageClass definitions
  """
  try:
    template = templates.load(STORAGE_TEMPLATE_PATH)

    manifest_path = save_manifest(args, manifest)
    fill_storage_template(template, args, manifest, manifest_path)
    save_storage_crds(k8s_api_client, template)
  except ApiException as e:
    if e.status == 409:
      xpk_print(f"Storage: {args.name} already exists. Skipping its creation")
    else:
      xpk_print(f"Encountered error during storage creation: {e}")
      xpk_exit(1)
