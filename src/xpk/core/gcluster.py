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

from typing import Callable
from xpk.core.docker_manager import CtkDockerManager
from xpk.core.docker_manager import ctk_dockerfile_path, ctk_docker_image
from docker.errors import ContainerError, ImageNotFound, APIError
import os
from xpk.utils.console import xpk_exit, xpk_print
from xpk.core.blueprint import CtkBlueprint
import ruamel.yaml

xpk_gcloud_cfg_path = '~/gcloud/cfg'
xpk_deployment_dir = '/deployment'
gcluster_deploy_command = 'gcluster deploy'
gcluster_create_command = 'gcluster create'
gcluster_destroy_command = 'gcluster destroy'
machine_ip = '10.0.0.0'
blueprint_file_name = 'xpk_blueprint.yaml'
ClusterToolkitErrorExitCode = 135
yaml = ruamel.yaml.YAML()
deployment_module = 'xpk-deployment'


class CtkManager:
  """_summary_"""

  def __init__(
      self,
      deployment_dir: str,
      blueprint: CtkBlueprint,
      dockerfile_path=ctk_dockerfile_path,
      gcloud_cfg_path=xpk_gcloud_cfg_path,
  ) -> None:
    self.deployment_dir = deployment_dir
    self.docker_manager = CtkDockerManager(
        dockerfile_path=dockerfile_path,
        gcloud_cfg_path=gcloud_cfg_path,
        deployment_dir=deployment_dir,
    )
    self.blueprint = blueprint
    self.docker_manager.build_image(img_name = ctk_docker_image)
    self._validate_deployment_dir()

  def _validate_deployment_dir(self):
    pass

  def add_to_deployment_dir(self) -> None:
    pass

  def _create_deployment_blueprint(self) -> str:
    xpk_print('Creating deployment blueprint')
    blueprint_file_path = os.path.join(self.deployment_dir, blueprint_file_name)
    with open(blueprint_file_path, 'wb') as blueprint_file:
      yaml.dump(self.blueprint, blueprint_file)
    xpk_print(f'Deployment blueprint saved at {blueprint_file_path}')
    return blueprint_file_path

  def _run_create_deployment_cmd(self):
    xpk_print('Creating deployment directory')
    blueprint_path = self._create_deployment_blueprint()
    cluster_create_cmd = f'{gcluster_create_command} {blueprint_path}'
    self.docker_manager.run_command(ctk_docker_image, cluster_create_cmd)

  def _run_deploy_cmd(self):
    xpk_print('Deploying created resources to cloud.')
    deploy_cmd = f'{gcluster_deploy_command} {deployment_module}'
    self.docker_manager.run_command(ctk_docker_image, deploy_cmd)
#create base class for docker run
# create dry run
# add stage_files
  def deploy(self) -> None:
    try:
      self._run_create_deployment_cmd()
      self._run_deploy_cmd()
    except ContainerError as e:
      xpk_print(
          'Deploying cluster failed due to ContainerError with exit status:'
          f' {e.exit_status} and stderr: {e.stderr}'
      )
      xpk_exit(ClusterToolkitErrorExitCode)
    except ImageNotFound as _:
      xpk_print(f'Image {ctk_docker_image} not found. Deploying cluster failed')
      xpk_exit(ClusterToolkitErrorExitCode)
    except APIError as e:
      xpk_print(f'Deploying cluster toolkit failed due to {e.explanation}')
      xpk_exit(ClusterToolkitErrorExitCode)

  def _run_destroy_command(self):
    deploy_cmd = f'{gcluster_destroy_command} {deployment_module}'
    self.docker_manager.run_command(ctk_docker_image, deploy_cmd)

  def destroy_deployment(self) -> None:
    try:
      self._run_destroy_command()
    except ContainerError as e:
      xpk_print(
          'Destroying cluster failed due to ContainerError with exit status:'
          f' {e.exit_status} and stderr: {e.stderr}'
      )
      xpk_exit(ClusterToolkitErrorExitCode)
    except ImageNotFound as _:
      xpk_print(
          f'Image {ctk_docker_image} not found. Destroying cluster failed'
      )
      xpk_exit(ClusterToolkitErrorExitCode)
    except APIError as e:
      xpk_print(f'Destroying cluster toolkit failed due to {e.explanation}')
      xpk_exit(ClusterToolkitErrorExitCode)
