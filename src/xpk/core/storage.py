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

import yaml
from kubernetes import client as k8s_client
from kubernetes import utils
from kubernetes.client import ApiClient
from kubernetes.client.exceptions import ApiException
from kubernetes.client.models.v1_persistent_volume import V1PersistentVolume
from kubernetes.utils import FailToCreateError
from tabulate import tabulate

from ..utils import xpk_exit, xpk_print

XPK_SA = "xpk-sa"
STORAGE_CRD_PATH = "/../api/storage_crd.yaml"
STORAGE_TEMPLATE_PATH = "/../templates/storage.yaml"
STORAGE_CRD_NAME = "storages.xpk.x-k8s.io"
STORAGE_CRD_KIND = "Storage"
XPK_API_GROUP_NAME = "xpk.x-k8s.io"
XPK_API_GROUP_VERSION = "v1"


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
      bucket: The name of the bucket PersistentVolume refers to.
  """

  name: str
  type: str
  cluster: str
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
    self.cluster: str = spec.get("cluster")
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
    except client.ApiException as e:
      xpk_print(
          f"Exception when calling CoreV1Api->read_persistent_volume: {e}"
      )
    return pv.spec.csi.volume_handle

  def get_mount_options(self) -> list[str]:
    """
    Retrieves the mount options for the PersistentVolume.

    Returns:
        A list of mount options.
    """
    client = k8s_client.CoreV1Api()
    try:
      pv: V1PersistentVolume = client.read_persistent_volume(self.pv)
    except client.ApiException as e:
      xpk_print(
          f"Exception when calling CoreV1Api->read_persistent_volume: {e}"
      )
    return pv.spec.mount_options


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
        plural=STORAGE_CRD_KIND.lower() + "s",
    )
  except ApiException as e:
    xpk_print(f"Kubernetes API exception while listing Storages: {e}")
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


def get_storages(k8s_api_client: ApiClient, names: list[str]) -> list[Storage]:
  """
  Retrieves a list of Storage resources by their names, including auto-mounted storages.

  Args:
      k8s_api_client: An ApiClient object for interacting with the Kubernetes API.
      names: A list of Storage resource names to retrieve.

  Returns:
      A list of Storage objects matching the given names and any auto-mounted storages.
  """
  storages: list[Storage] = []
  for storage in list_storages(k8s_api_client):
    if storage.name in names:
      storages.append(storage)

  for auto_mounted_stg in get_auto_mount_storages(k8s_api_client):
    # prevent duplicating storages
    if auto_mounted_stg.name not in names:
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
        plural=STORAGE_CRD_KIND.lower() + "s",
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


def print_storages_for_cluster(storages: list[Storage], cluster: str):
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
    if storage.cluster == cluster:
      storage_tab.append(storage.fields_as_list())

  print(
      tabulate(
          storage_tab,
          headers=headers,
      )
  )


def create_storage_instance(k8s_api_client: ApiClient, args: Namespace) -> None:
  """
  Creates a new Storage custom resource in the Kubernetes cluster.

  This function reads a Storage template from a YAML file, populates it with
  values from the provided arguments, and then creates the Storage object
  in the cluster.

  Args:
      k8s_api_client: An ApiClient object for interacting with the Kubernetes API.
      args: An argparse Namespace object containing the arguments for creating
            the Storage resource.
  """
  abs_path = f"{os.path.dirname(__file__)}{STORAGE_TEMPLATE_PATH}"
  with open(abs_path, "r", encoding="utf-8") as file:
    data = yaml.safe_load(file)

  data["metadata"]["name"] = args.name
  spec = data["spec"]
  spec["cluster"] = args.cluster
  spec["type"] = args.type
  spec["auto_mount"] = args.auto_mount
  spec["mount_point"] = args.mount_point
  spec["readonly"] = args.readonly
  spec["manifest"] = args.manifest

  with open(args.manifest, "r", encoding="utf-8") as f:
    pv_pvc_definitions = yaml.safe_load_all(f)
    for obj in pv_pvc_definitions:
      if obj["kind"] == "PersistentVolume":
        spec["pv"] = obj["metadata"]["name"]
      elif obj["kind"] == "PersistentVolumeClaim":
        spec["pvc"] = obj["metadata"]["name"]

  data["spec"] = spec

  api_instance = k8s_client.CustomObjectsApi(k8s_api_client)
  xpk_print(f"Creating a new Storage: {args.name}")
  try:
    api_instance.create_cluster_custom_object(
        group=XPK_API_GROUP_NAME,
        version=XPK_API_GROUP_VERSION,
        plural=STORAGE_CRD_KIND.lower() + "s",
        body=data,
    )
    xpk_print(f"Created {STORAGE_CRD_KIND} object: {data['metadata']['name']}")
  except ApiException as e:
    if e.status == 409:
      xpk_print(f"Storage: {args.name} already exists. Skipping its creation")
    else:
      xpk_print(f"Encountered error during storage creation: {e}")
      xpk_exit(1)
