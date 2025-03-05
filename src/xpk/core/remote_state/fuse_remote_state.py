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
  """FuseStateClient is a class for managing remote xpk state stored in GCS Fuse."""

  def __init__(
      self,
      bucket: str,
      state_directory: str,
      cluster: str,
      deployment_name: str,
      prefix: str,
  ) -> None:
    self.bucket = bucket
    self.state_dir = state_directory
    self.storage_client = Client()
    self.cluster = cluster
    self.prefix = prefix
    self.deployment_name = deployment_name

  def _get_bucket_path(self) -> str:
    return (
        f'xpk_terraform_state/{self.prefix}/blueprints/{self.deployment_name}/'
    )

  def _get_bucket_path_blueprint(self) -> str:
    return f'xpk_terraform_state/{self.prefix}/blueprints/'

  def _get_deployment_filename(self) -> str:
    return f'{self.deployment_name}.yaml'

  def _get_blueprint_path(self) -> str:
    blueprint_dir = '/'.join(self.state_dir.split('/')[:-1])
    return os.path.join(blueprint_dir, self.deployment_name) + '.yaml'

  def upload_state(self) -> None:
    xpk_print(
        f'Uploading dependecies from directory {self.state_dir} to bucket:'
        f' {self.bucket}. Path within bucket is: {self._get_bucket_path()}'
    )
    upload_directory_to_gcs(
        storage_client=self.storage_client,
        bucket_name=self.bucket,
        bucket_path=self._get_bucket_path(),
        source_directory=self.state_dir,
    )
    blueprint_bucket_path = (
        self._get_bucket_path_blueprint() + self._get_deployment_filename()
    )
    xpk_print(
        f'Uploading blueprint file: {self._get_blueprint_path()} to bucket'
        f' {self.bucket}. Path within bucket is: {blueprint_bucket_path}'
    )
    upload_file_to_gcs(
        storage_client=self.storage_client,
        bucket_name=self.bucket,
        bucket_path=blueprint_bucket_path,
        file=self._get_blueprint_path(),
    )

  def download_state(self) -> None:
    xpk_print(
        f'Downloading from bucket: {self.bucket}, from path:'
        f' {self._get_bucket_path()} to directory: {self.state_dir}'
    )
    download_bucket_to_dir(
        self.storage_client,
        self.bucket,
        self._get_bucket_path(),
        destination_directory=self.state_dir,
    )

  def check_remote_state_exists(self) -> bool:
    return check_file_exists(
        self.storage_client,
        self.bucket,
        self._get_bucket_path_blueprint() + self._get_deployment_filename(),
    )
