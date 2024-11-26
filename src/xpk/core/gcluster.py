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

from xpk.core.docker_manager import CtkDockerManager
from xpk.core.docker_manager import ctk_dockerfile_path, ctk_docker_image

xpk_gcloud_cfg_path = '~/gcloud/cfg'
xpk_deployment_dir = '/deployment'
gcluster_deploy_command = 'gcluster deploy'
gcluster_create_command = 'gcluster create'
gcluster_destroy_command = 'gcluster destroy'


class CtkManager:
  """_summary_"""

  def __init__(
      self,
      deployment_dir: str,
      dockerfile_path=ctk_dockerfile_path,
      gcloud_cfg_path=xpk_gcloud_cfg_path,
  ) -> None:
    self.deployment_dir = deployment_dir
    self.docker_manager = CtkDockerManager(
        dockerfile_path=dockerfile_path,
        gcloud_cfg_path=gcloud_cfg_path,
        deployment_dir=deployment_dir,
    )
    self.docker_manager.build_image()
    self._validate_deployment_dir()

  def _validate_deployment_dir(self):
    pass

  def add_to_deployment_dir(self) -> None:
    pass

  def deploy(self) -> None:
    blueprint_path = 'foo.yaml'
    cluster_create_cmd = f'{gcluster_create_command} {blueprint_path}'
    self.docker_manager.run_command(ctk_docker_image, cluster_create_cmd)
    deployment_module = 'xpk-deployment'
    deploy_cmd = f'{gcluster_deploy_command} {deployment_module}'
    self.docker_manager.run_command(ctk_docker_image, deploy_cmd)

  def destroy_deployment(self) -> None:
    pass
