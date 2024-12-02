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
from ..utils import xpk_print


class FilestoreClient:
  """_summary_"""

  def __init__(self, region: str, zone: str, name: str, project: str) -> None:
    self.region = region
    self.zone = zone
    self.name = name
    self.project = project

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
    client = filestore_v1.CloudFilestoreManagerClient()
    parent = f"projects/{self.project}/location/{self.zone}"
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
    operation = client.create_instance(request=request)

    xpk_print("Waiting for operation to complete...")

    response = operation.result()

    # Handle the response
    print(response)

  def create_pv_pvc_yaml(self, filepath: str) -> None:
    """Create a yaml representing filestore PV and PVC and save it to file.

    Args:
        filepath (str): path to which yaml file containing PV and PVC will be saved

    Returns:
      None
    """
