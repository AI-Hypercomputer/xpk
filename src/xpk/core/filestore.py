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

from google.cloud import filestore_v1

from google.cloud.filestore_v1.types import Instance
from google.cloud.filestore_v1.types import FileShareConfig
from google.cloud.filestore_v1.types import NetworkConfig
from google.cloud.exceptions import GoogleCloudError

from ..utils.console import xpk_exit, xpk_print
from .cluster import zone_to_region
from enum import Enum

import os
import ruamel.yaml

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

  def __init__(self, zone: str, name: str, project: str, tier: str) -> None:
    self.zone = zone
    self.region = zone_to_region(zone)
    self.tier = tier
    self.availability = TIERS[tier].value
    self.name = name
    self.project = project
    self._client = filestore_v1.CloudFilestoreManagerClient()

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
        return True

    for instance in instancesRegional:
      if instance.name == fullname_regional:
        return True

    return False

  def create_filestore_instance(
      self,
      vol: str,
      size: int,
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
            tier=self.tier,
            kms_key_name=kms_key_name,
            file_shares=file_shares,
            networks=networks,
        ),
    )

    # Make the request
    operation = self._client.create_instance(request=request)
    xpk_print("Waiting for filestore creation to complete...")
    self.response = None
    try:
      self.response = operation.result()
    except GoogleCloudError as e:
      xpk_print(f"Error while creating Filestore instance: {e}")
      xpk_exit(1)
    xpk_print(f"Filestore instance {self.get_parent()} created")

  def delete_filestore_instance(self):
    # Initialize request
    request = filestore_v1.DeleteInstanceRequest(name=self.name)

    # Make the request
    operation = self._client.delete_instance(request)
    xpk_print("WAiting for filestore deletion to complete...")
    response = None
    try:
      response = operation.result()
    except GoogleCloudError as e:
      xpk_print(f"Error while deleting Filestore instance: {e}")
      xpk_exit(1)
    xpk_print(f"Filestore instance {self.get_parent()} deleted")
    self.response = response

  def create_sc(self, network: str, project: str) -> dict:
    abs_path = f"{os.path.dirname(__file__)}{FS_SC_PATH}"
    with open(abs_path, "r", encoding="utf-8") as file:
      data: dict = yaml.load(file)
    data["metadata"]["name"] = get_storage_class_name(self.name)
    data["parameters"]["tier"] = self.tier
    data["parameters"][
        "network"
    ] = f"projects/{project}/global/networks/{network}"
    return data

  def create_pv(self, vol: str, access_mode: str) -> dict:
    abs_path = f"{os.path.dirname(__file__)}{FS_PV_PATH}"
    with open(abs_path, "r", encoding="utf-8") as file:
      data: dict = yaml.load(file)

    data["metadata"]["name"] = get_pv_name(self.name)
    spec = data["spec"]
    spec["storageClassName"] = get_storage_class_name(self.name)
    spec["capacity"]["storage"] = self.response.file_shares[0].capacity_gb
    spec["accessModes"] = [access_mode]
    volumeHandle = f"{self.get_instance_fullname()}/volumes/{vol}"
    spec["csi"]["volumeHandle"] = volumeHandle
    spec["csi"]["volumeAttributes"]["ip"] = self.response.networks[
        0
    ].ip_addresses[0]
    spec["csi"]["volumeAttributes"]["volume"] = vol
    data["spec"] = spec
    return data

  def create_pvc(self, access_mode: str) -> dict:
    """Create a yaml representing filestore PV and PVC and save it to file.

    Args:
        filepath (str): path to which yaml file containing PV and PVC will be saved

    Returns:
      None
    """
    abs_path = f"{os.path.dirname(__file__)}{FS_PVC_PATH}"
    with open(abs_path, "r", encoding="utf-8") as file:
      data: dict = yaml.load(file)
    data["metadata"]["name"] = get_pvc_name(self.name)
    spec = data["spec"]
    spec["accessModes"] = [access_mode]
    spec["storageClassName"] = get_storage_class_name(self.name)
    spec["volumeName"] = get_pv_name(self.name)
    spec["resources"]["requests"]["storage"] = self.response.file_shares[
        0
    ].capacity_gb
    data["spec"] = spec
    return data

  def get_location(self) -> str:
    """Get gcp location based on the Filestore's tier"""
    return (
        self.region
        if self.availability == Availability.REGIONAL.value
        else self.zone
    )

  def get_parent(self, location: str | None = None) -> str:
    """Get the Filestore's name's parent"""
    if location is None:
      location = self.get_location()
    return f"projects/{self.project}/locations/{location}"

  def get_instance_fullname(self, parent: str | None = None) -> str:
    """Get the Filestore's name's parent"""
    if parent is None:
      parent = self.get_parent()
    return f"{parent}/instances/{self.name}"

  def compile_to_manifest_yaml(
      self, manifests_path: str, sc: dict, pv: dict, pvc: dict
  ) -> str:
    manifest_file = (
        f"{manifests_path}/{self.project}-{self.zone}-{self.name}-manifest.yaml"
    )
    with open(manifest_file, mode="w+", encoding="utf-8") as f:
      yaml.dump(sc, f)
      f.write(yaml_object_separator)
      yaml.dump(pv, f)
      f.write(yaml_object_separator)
      yaml.dump(pvc, f)
    return manifest_file
