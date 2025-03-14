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

from enum import Enum

from google.cloud import filestore_v1
from google.cloud.exceptions import GoogleCloudError
from google.cloud.filestore_v1.types import (
    FileShareConfig,
    Instance,
    NetworkConfig,
)

from ..utils import templates
from ..utils.console import xpk_exit, xpk_print
from .cluster import zone_to_region

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
    self.instance: Instance | None = None

  def get_instance(self) -> Instance | None:
    """Get existing Filestore instance"""
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

    fullname_zonal = self.get_instance_fullname(self.zone)
    fullname_regional = self.get_instance_fullname(self.region)

    for instance in instancesZonal:
      if instance.name == fullname_zonal:
        return instance  # pytype: disable=bad-return-type

    for instance in instancesRegional:
      if instance.name == fullname_regional:
        return instance  # pytype: disable=bad-return-type

  def check_instance_exists(self) -> bool:
    """Check if Filestore instance exists"""
    instance = self.get_instance()
    return instance is not None

  def load_instance(self) -> None:
    if self.instance is None:
      self.instance = self.get_instance()

  def get_instance_location(self) -> str:
    """Get Filestore instance's location"""
    self.load_instance()
    return str(self.instance.name.split("/")[3])

  def create_instance(
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

    location = (
        self.zone
        if TIERS[tier].value == Availability.ZONAL.value
        else self.region
    )

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
        parent=self.get_parent(location),
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
    xpk_print(
        f"Filestore instance {self.get_instance_fullname(location)} created"
    )

  def delete_filestore_instance(self):
    # Initialize request
    name = self.get_instance_fullname()
    request = filestore_v1.DeleteInstanceRequest(name=name)

    # Make the request
    operation = self._client.delete_instance(request)
    xpk_print("Waiting for filestore deletion to complete...")
    try:
      operation.result()
    except GoogleCloudError as e:
      xpk_print(f"Error while deleting Filestore instance: {e}")
      xpk_exit(1)
    xpk_print(f"Filestore instance {name} deleted")

  def create_sc(self, name: str, network: str) -> dict:
    """Create a yaml representing filestore StorageClass."""
    data = templates.load(FS_SC_PATH)
    data["metadata"]["name"] = get_storage_class_name(name)
    data["parameters"]["tier"] = self.instance.tier.name
    data["parameters"][
        "network"
    ] = f"projects/{self.project}/global/networks/{network}"
    return data

  def create_pv(self, name: str, vol: str, access_mode: str) -> dict:
    """Create a yaml representing filestore PersistentVolume."""
    data = templates.load(FS_PV_PATH)
    data["metadata"]["name"] = get_pv_name(name)
    data["spec"]["storageClassName"] = get_storage_class_name(name)
    data["spec"]["capacity"]["storage"] = self.instance.file_shares[
        0
    ].capacity_gb
    data["spec"]["accessModes"] = [access_mode]
    volumeHandle = f"{self.get_instance_fullname()}/volumes/{vol}"
    data["spec"]["csi"]["volumeHandle"] = volumeHandle
    data["spec"]["csi"]["volumeAttributes"]["ip"] = self.instance.networks[
        0
    ].ip_addresses[0]
    data["spec"]["csi"]["volumeAttributes"]["volume"] = vol
    return data

  def create_pvc(self, name: str, access_mode: str) -> dict:
    """Create a yaml representing filestore PersistentVolumeClaim."""
    data = templates.load(FS_PVC_PATH)
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
    self.load_instance()
    pv = self.create_pv(name, vol, access_mode)
    pvc = self.create_pvc(name, access_mode)
    sc = self.create_sc(name, network)
    return [pv, pvc, sc]

  def get_parent(self, location: str | None = None) -> str:
    """Get the Filestore's parent's name"""
    if location is None:
      location = self.get_instance_location()
    return f"projects/{self.project}/locations/{location}"

  def get_instance_fullname(self, location: str | None = None) -> str:
    """Get the Filestore's full name"""
    if location is None:
      location = self.get_instance_location()
    return f"projects/{self.project}/locations/{location}/instances/{self.name}"
