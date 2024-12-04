"""
Copyright 2023 Google LLC

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
from ..utils import xpk_exit, xpk_print
import json
import os
import ruamel.yaml

yaml = ruamel.yaml.YAML()

FS_MANIFEST_PATH = "/../templates/fs-manifest.yaml"


class FilestoreClient:
  """_summary_"""

  def __init__(self, zone: str, name: str, project: str) -> None:
    self.zone = zone
    self.name = name
    self.project = project
    self._client = filestore_v1.CloudFilestoreManagerClient()

  def check_filestore_instance_exists(self, instance_id: str) -> bool:
    parent = f"projects/{self.project}/locations/{self.zone}"
    req = filestore_v1.ListInstancesRequest(parent=parent)
    try:
      instances = self._client.list_instances(req)
    except GoogleCloudError as e:
      xpk_print(f"Exception while trying to list instances {e}")
      xpk_exit(1)

    for instance in instances:
      if instance.name == f"{parent}/instances/{instance_id}":
        return True
    return False

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

    parent = f"projects/{self.project}/locations/{self.zone}"
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
        parent=parent,
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
    response = None
    try:
      response = operation.result()
    except GoogleCloudError as e:
      xpk_print(f"Error while creating Filestore instance: {e}")
      xpk_exit(1)
    xpk_print(f"Filestore instance {parent} created")
    self.response = response

  def create_pv_pvc_yaml(self, filepath: str) -> None:
    """Create a yaml representing filestore PV and PVC and save it to file.

    Args:
        filepath (str): path to which yaml file containing PV and PVC will be saved

    Returns:
      None
    """

    print(self.response)
    abs_path = f"{os.path.dirname(__file__)}{FS_MANIFEST_PATH}"
    with open(abs_path, "r", encoding="utf-8") as file:
      data = yaml.load(file)

    print(data)
  
