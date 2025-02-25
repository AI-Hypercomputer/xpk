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
from ...utils.gcs_utils import upload_directory_to_gcs, check_file_exists, download_bucket_to_dir, upload_file_to_gcs
from ...utils.console import xpk_print
from google.cloud.storage import Client
import os


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
    return f'xpk_terraform_state/{self.project}-{self.zone}-{self.deployment_name}/{self.deployment_name}/'

  def _get_bucket_path_blueprint(self) -> str:
    return f'xpk_terraform_state/{self.project}-{self.zone}-{self.deployment_name}/'

  def _get_deployment_filename(self) -> str:
    return f'{self.deployment_name}.yaml'

  def _get_blueprint_path(self) -> str:
    blueprint_dir = '/'.join(self.state_dir.split('/')[:-1])
    return os.path.join(blueprint_dir, self.deployment_name) + '.yaml'

  def upload_state(self) -> None:
    upload_directory_to_gcs(
        storage_client=self.storage_client,
        bucket_name=self.bucket,
        bucket_path=self._get_bucket_path(),
        source_directory=self.state_dir,
    )
    xpk_print('Uploading blueprint to bucket')
    upload_file_to_gcs(
        storage_client=self.storage_client,
        bucket_name=self.bucket,
        bucket_path=self._get_bucket_path_blueprint()
        + self._get_deployment_filename(),
        file=self._get_blueprint_path(),
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
        self.bucket,
        self._get_bucket_path_blueprint()
        + self._get_deployment_filename(),
    )
