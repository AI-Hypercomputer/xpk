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

from .docker_manager import CommandRunner
from ..utils.console import xpk_exit, xpk_print
from .remote_state.remote_state_client import RemoteStateClient

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
    - gcluster_command_runner (CommandRunner) : instance of class implementing CommandRunner abstract methods.
  Methods:
    - deploy : run a deployment process of cluster toolkit. This method will invoke gcluster create and than gcluster deploy commands.
    - destroy_deployment : run gcluster command to destroy existing deployment.
  """

  def __init__(
      self,
      gcluster_command_runner: CommandRunner,
      remote_state_client: RemoteStateClient | None,
  ) -> None:
    self.gcluster_command_runner = gcluster_command_runner
    self.remote_state_client = remote_state_client

  def _run_create_deployment_cmd(
      self, blueprint_container_path: str, prefix: str = ''
  ):
    xpk_print('Creating deployment resources...')
    cluster_create_cmd = (
        f'{gcluster_create_command} -o {self._get_deployment_path(prefix)}'
        f' {blueprint_container_path} -w --force'
    )
    self.gcluster_command_runner.run_command(cluster_create_cmd)
    xpk_print('Creating deployment resources completed.')

  def _run_deploy_cmd(
      self,
      deployment_name: str,
      auto_approve: bool,
      dry_run: bool,
      prefix: str = '',
  ):
    xpk_print('Deploying resources...')
    deploy_cmd = (
        f'{gcluster_deploy_command} {self._get_deployment_path(prefix)}/{deployment_name}'
    )
    if auto_approve is True:
      deploy_cmd += ' --auto-approve'
    if dry_run is True:
      return
    self.gcluster_command_runner.run_command(deploy_cmd)
    xpk_print('Deployment completed.')

  def deploy(
      self,
      blueprint_path: str,
      deployment_name: str,
      prefix: str = '',
      auto_approve: bool = True,
      dry_run: bool = False,
  ) -> None:
    """ "deploy method provisions a new cluster using Cluster Toolkit.
    It will invoke gcluster create and then gcluster deploy commands.
    The files staged or created during running gcluster command will be managed by gcluster_command_runner in its working directory."

    Args:
        blueprint_path (str): path pointing to blueprint which will be deployed.
        deployment_name (str): name of the deployment.
        auto_approve (bool, optional): If set to true deployment command will be auto approved. Currently only True is supported. Defaults to True.
        dry_run (bool, optional): If set to True gcluster will not deploy. Defaults to False.
    Returns:
      None
    """
    xpk_print(f'Deploying blueprint from path {blueprint_path} ...')
    self._run_create_deployment_cmd(
        blueprint_container_path=blueprint_path, prefix=prefix
    )
    self._run_deploy_cmd(
        deployment_name=deployment_name,
        prefix=prefix,
        auto_approve=auto_approve,
        dry_run=dry_run,
    )
    xpk_print('Deploying blueprint completed!')

  def _run_destroy_command(
      self,
      deployment_name: str,
      prefix: str = '',
      auto_approve: bool = True,
      dry_run: bool = False,
  ):
    destroy_cmd = (
        f'{gcluster_destroy_command} {self._get_deployment_path(prefix)}/{deployment_name}'
    )
    if auto_approve is True:
      destroy_cmd += ' --auto-approve'
    if dry_run is True:
      xpk_print(f'executing command {destroy_cmd}')
      return
    self.gcluster_command_runner.run_command(destroy_cmd)

  def _get_deployment_path(self, prefix: str = '') -> str:
    prefix = f'/{prefix}' if prefix != '' else ''
    return f'deployments{prefix}'

  def destroy_deployment(self, deployment_name: str, prefix: str = '') -> None:
    """Destroy deployment.

    Args:
        deployment_name (str): name of deployment to destroy.
    """
    xpk_print(f'Destroying {deployment_name} started...')
    self._run_destroy_command(deployment_name, prefix=prefix)
    xpk_print(f'Destroying {deployment_name} completed!')

  def stage_files(
      self, blueprint_file: str, blueprint_dependencies: str, prefix: str = ''
  ) -> str:
    """Uploads blueprint file and directory to gcluster working directory."""
    xpk_print(
        "Staging (sending) blueprint file to gcluster's working directory..."
    )
    staged_blueprint = self.gcluster_command_runner.upload_file_to_working_dir(
        blueprint_file, prefix
    )
    if len(blueprint_dependencies) > 0:
      self.gcluster_command_runner.upload_directory_to_working_dir(
          blueprint_dependencies, prefix
      )
    xpk_print('Staging blueprint completed!')
    xpk_print(f"File path in gcluster's working directory: {staged_blueprint}")
    return staged_blueprint

  def upload_state(self) -> None:
    xpk_print('Uploading state.')
    if self.remote_state_client is None:
      xpk_print('No remote state defined')
      xpk_exit(1)
    self.remote_state_client.upload_state()

  def download_state(self) -> None:
    if self.remote_state_client is None:
      xpk_print('No remote state defined')
      xpk_exit(1)

    if self.remote_state_client.check_remote_state_exists():
      self.remote_state_client.download_state()
    xpk_print('Remote state not found.')
