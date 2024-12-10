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

from xpk.core.docker_manager import CommandRunner
from xpk.utils.console import xpk_print


xpk_gcloud_cfg_path = '~/gcloud/cfg'
xpk_deployment_dir = '/deployment'
gcluster_deploy_command = 'gcluster deploy'
gcluster_create_command = 'gcluster create'
gcluster_destroy_command = 'gcluster destroy'
blueprint_file_name = 'xpk_blueprint.yaml'
deployment_module = '/out/xpk-deployment'
a3_utils_dir_name = 'a3-mega-xpk'
config_map_repo_path = 'src/xpk/blueprints/a3-mega-xpk/config-map.yaml.tftpl'
kueue_config_repo_path = (
    'src/xpk/blueprints/a3-mega-xpk/kueue-xpk-configuration.yaml.tftpl'
)


class GclusterManager:
  """Manager is a class responsible for running cluster toolkit commands.
  Attributes:
    - deployment_dir (str) : directory containing all files used during building deployment files. It should contain blupeprint file inside:
      deployment_dir:
        - blueprint.yaml
        - dir_used_in_blueprint
    - gcluster_command_runner (CommandRunner) : instance of class implementing CommandRunner abstract methods.
  Methods:
    - deploy : run a deployment process of cluster toolkit. This method will invoke gcluster create and than gcluster deploy commands.
    - destroy_deployment : run gcluster command to destroy existing deployment.
  """

  def __init__(
      self,
      gcluster_command_runner: CommandRunner,
  ) -> None:
    self.gcluster_command_runner = gcluster_command_runner

  def _run_create_deployment_cmd(self, blueprint_container_path: str):
    xpk_print('Creating deployment directory')
    cluster_create_cmd = (
        f'{gcluster_create_command} -o deployments {blueprint_container_path}'
    )
    self.gcluster_command_runner.run_command(cluster_create_cmd)

  def _run_deploy_cmd(
      self, deployment_name: str, auto_approve: bool, dry_run: bool
  ):
    xpk_print('Deploying created resources to cloud.')
    deploy_cmd = f'{gcluster_deploy_command} deployments/{deployment_name}'
    if auto_approve is True:
      deploy_cmd += ' --auto-approve'
    if dry_run is True:
      return
    self.gcluster_command_runner.run_command(deploy_cmd)

  def deploy(
      self,
      blueprint_path: str,
      deployment_name: str,
      auto_approve: bool = True,
      dry_run: bool = False,
  ) -> None:
    blueprint_name = blueprint_path.split('/')[-1]
    blueprint_container_path = f'/out/{blueprint_name}'
    self._run_create_deployment_cmd(
        blueprint_container_path=blueprint_container_path
    )
    self._run_deploy_cmd(
        deployment_name=deployment_name,
        auto_approve=auto_approve,
        dry_run=dry_run,
    )

  def _run_destroy_command(
      self,
      deployment_name: str,
      auto_approve: bool = True,
      dry_run: bool = False,
  ):
    destroy_cmd = f'{gcluster_destroy_command} deployments/{deployment_name}'
    if auto_approve is True:
      destroy_cmd += ' --auto-approve'
    if dry_run is True:
      xpk_print(f'executing command {destroy_cmd}')
    self.gcluster_command_runner.run_command(destroy_cmd)

  def destroy_deployment(self, deployment_name: str) -> None:
    self._run_destroy_command(deployment_name)

  def stage_files(
      self, blueprint_file: str, blueprint_dependencies: str
  ) -> str:
    """Download files neccessary for deployment to deployment directory."""
    staged_blueprint = self.gcluster_command_runner.upload_file_to_working_dir(
        blueprint_file
    )
    if len(blueprint_dependencies) == 0:
      return staged_blueprint
    self.gcluster_command_runner.upload_directory_to_working_dir(
        blueprint_dependencies
    )
    return staged_blueprint
