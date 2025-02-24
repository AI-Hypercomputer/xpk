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

from .remote_state_client import RemoteStateClient
from ...utils.gcs_utils import upload_directory_to_gcs, check_file_exists, download_bucket_to_dir

from google.cloud.storage import Client


class FuseStateClient(RemoteStateClient):
  """_summary_"""

  def __init__(
      self,
      bucket: str,
      state_directory: str,
      project: str,
      zone: str,
      deployment_name: str,
  ) -> None:
    self.bucket = bucket
    self.state_dir = state_directory
    self.project = project
    self.zone = zone
    self.storage_client = Client()
    self.deployment_name = deployment_name

  def _get_bucket_path(self) -> str:
    return f'{self.bucket}/xpk_terraform_state/{self.project}-{self.zone}-{self.deployment_name}'

  def _get_deployment_filename(self) -> str:
    return f'{self.deployment_name}.yaml'

  def upload_state(self) -> None:
    upload_directory_to_gcs(
        storage_client=self.storage_client,
        bucket_name=self._get_bucket_path(),
        source_directory=self.state_dir,
    )

  def download_state(self) -> None:
    download_bucket_to_dir(
        self.storage_client,
        self._get_bucket_path(),
        destination_directory=self.state_dir,
    )

  def check_remote_state_exists(self) -> bool:
    return check_file_exists(
        self.storage_client,
        self._get_bucket_path(),
        self._get_deployment_filename(),
    )
