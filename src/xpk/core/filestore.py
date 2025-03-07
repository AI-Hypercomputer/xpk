"""
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
"""

import os
from enum import Enum

import ruamel.yaml
from google.cloud import filestore_v1
from google.cloud.exceptions import GoogleCloudError
from google.cloud.filestore_v1.types import (
    FileShareConfig,
    Instance,
    NetworkConfig,
)

from ..utils.console import xpk_exit, xpk_print
from .cluster import zone_to_region

yaml = ruamel.yaml.YAML()
yaml_object_separator = "---\n"

FS_PV_PATH = "/../templates/filestore-pv.yaml"
FS_PVC_PATH = "/../templates/filestore-pvc.yaml"
FS_SC_PATH = "/../templates/filestore-sc.yaml"


class Availability(Enum):
  ZONAL = "Zonal"
  REGIONAL = "Regional"


TIERS = {
    "BASIC_HDD": Availability.ZONAL,
    "BASIC_SSD": Availability.ZONAL,
    "ZONAL": Availability.ZONAL,
    "REGIONAL": Availability.REGIONAL,
    "ENTERPRISE": Availability.REGIONAL,
}


def get_storage_class_name(storage_name: str) -> str:
  return f"{storage_name}-sc"


def get_pv_name(storage_name: str) -> str:
  return f"{storage_name}-pv"


def get_pvc_name(storage_name: str) -> str:
  return f"{storage_name}-pvc"


class FilestoreClient:
  """FilestoreClient is a class for interacting with GCP filestore instances."""

  def __init__(
      self,
      zone: str,
      name: str,
      project: str,
  ) -> None:
    self.zone = zone
    self.region = zone_to_region(zone)
    self.name = name
    self.project = project
    self._client = filestore_v1.CloudFilestoreManagerClient()
    self.location: str | None = None
    self.instance: Instance | None = None

  def check_filestore_instance_exists(
      self,
  ) -> bool:
    parentZonal = self.get_parent(self.zone)
    parentRegional = self.get_parent(self.region)
    reqZonal = filestore_v1.ListInstancesRequest(parent=parentZonal)
    reqRegional = filestore_v1.ListInstancesRequest(parent=parentRegional)
    try:
      instancesZonal = self._client.list_instances(reqZonal)
      instancesRegional = self._client.list_instances(reqRegional)
    except GoogleCloudError as e:
      xpk_print(f"Exception while trying to list instances {e}")
      xpk_exit(1)

    fullname_zonal = self.get_instance_fullname(parentZonal)
    fullname_regional = self.get_instance_fullname(parentRegional)

    for instance in instancesZonal:
      if instance.name == fullname_zonal:
        self.location = self.zone
        return True

    for instance in instancesRegional:
      if instance.name == fullname_regional:
        self.location = self.region
        return True

    return False

  def load_instance(self) -> None:
    """Load existing filestore instance"""
    instance_name = self.get_instance_fullname()
    request = filestore_v1.GetInstanceRequest(name=instance_name)
    self.instance = self._client.get_instance(request)

  def create_filestore_instance(
      self,
      vol: str,
      size: int,
      tier: str,
      connect_mode=None,
      reserved_ip_range=None,
      network: str = "default",
      description: str = "XPK created filestore instance",
      kms_key_name=None,
      source_backup=None,
      nfs_export_options=None,
      modes=None,
  ) -> None:
    """Create new Filestore instance"""

    self.location = self.zone if TIERS[tier].value == "Zonal" else self.region

    file_shares = [
        FileShareConfig(
            name=vol,
            capacity_gb=size,
            source_backup=source_backup,
            nfs_export_options=nfs_export_options,
        )
    ]
    networks = [
        NetworkConfig(
            network=network,
            modes=modes,
            reserved_ip_range=reserved_ip_range,
            connect_mode=connect_mode,
        )
    ]
    request = filestore_v1.CreateInstanceRequest(
        parent=self.get_parent(),
        instance_id=self.name,
        instance=Instance(
            description=description,
            tier=tier,
            kms_key_name=kms_key_name,
            file_shares=file_shares,
            networks=networks,
        ),
    )
    # Make the request
    operation = self._client.create_instance(request=request)
    xpk_print("Waiting for filestore creation to complete...")
    self.instance = None
    try:
      self.instance = operation.result()
    except GoogleCloudError as e:
      xpk_print(f"Error while creating Filestore instance: {e}")
      xpk_exit(1)
    xpk_print(f"Filestore instance {self.get_parent()} created")

  def create_sc(self, name: str, network: str) -> dict:
    """Create a yaml representing filestore StorageClass."""
    if self.instance is None:
      xpk_print(
          f"Filestore instance {self.name} does not exist or was not loaded."
      )
      xpk_exit(1)
    template_path = os.path.dirname(__file__) + FS_SC_PATH
    with open(template_path, "r", encoding="utf-8") as file:
      data: dict = yaml.load(file)
    data["metadata"]["name"] = get_storage_class_name(name)
    data["parameters"]["tier"] = self.instance.tier.name
    data["parameters"][
        "network"
    ] = f"projects/{self.project}/global/networks/{network}"
    return data

  def create_pv(self, name: str, vol: str, access_mode: str) -> dict:
    """Create a yaml representing filestore PersistentVolume."""
    if self.instance is None:
      xpk_print(
          f"Filestore instance {self.name} does not exist or was not loaded."
      )
      xpk_exit(1)
    template_path = os.path.dirname(__file__) + FS_PV_PATH
    with open(template_path, "r", encoding="utf-8") as file:
      data: dict = yaml.load(file)

    data["metadata"]["name"] = get_pv_name(name)
    data["spec"]["storageClassName"] = get_storage_class_name(name)
    data["spec"]["capacity"]["storage"] = self.instance.file_shares[
        0
    ].capacity_gb
    data["spec"]["accessModes"] = [access_mode]
    parent = self.get_parent()
    volumeHandle = f"{self.get_instance_fullname(parent)}/volumes/{vol}"
    data["spec"]["csi"]["volumeHandle"] = volumeHandle
    data["spec"]["csi"]["volumeAttributes"]["ip"] = self.instance.networks[
        0
    ].ip_addresses[0]
    data["spec"]["csi"]["volumeAttributes"]["volume"] = vol
    return data

  def create_pvc(self, name: str, access_mode: str) -> dict:
    """Create a yaml representing filestore PersistentVolumeClaim."""
    if self.instance is None:
      xpk_print(
          f"Filestore instance {self.name} does not exist or was not loaded."
      )
      xpk_exit(1)
    template_path = os.path.dirname(__file__) + FS_PVC_PATH
    with open(template_path, "r", encoding="utf-8") as file:
      data: dict = yaml.load(file)
    data["metadata"]["name"] = get_pvc_name(name)
    data["spec"]["accessModes"] = [access_mode]
    data["spec"]["storageClassName"] = get_storage_class_name(name)
    data["spec"]["volumeName"] = get_pv_name(name)
    data["spec"]["resources"]["requests"]["storage"] = (
        self.instance.file_shares[0].capacity_gb
    )
    return data

  def manifest(
      self, name: str, vol: str, access_mode: str, network: str
  ) -> list[dict]:
    pv = self.create_pv(name, vol, access_mode)
    pvc = self.create_pvc(name, access_mode)
    sc = self.create_sc(name, network)
    return [pv, pvc, sc]

  def load_location(self) -> str:
    """Load and return filestore location"""
    if self.location is not None:
      return str(self.location)

    if not self.check_filestore_instance_exists():
      xpk_print(f"Filestore instance {self.name} not found")
      xpk_exit(1)

    return str(self.location)

  def get_parent(self, location: str | None = None) -> str:
    """Get the Filestore's parent's name"""
    if location is None:
      location = self.load_location()
    return f"projects/{self.project}/locations/{location}"

  def get_instance_fullname(self, parent: str | None = None) -> str:
    """Get the Filestore's full name"""
    if parent is None:
      parent = self.get_parent()
    return f"{parent}/instances/{self.name}"
