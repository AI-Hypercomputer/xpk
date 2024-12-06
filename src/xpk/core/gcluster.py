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

from xpk.core.docker_manager import CtkCommandRunner
from xpk.utils.console import xpk_print
import os
import shutil

xpk_gcloud_cfg_path = '~/gcloud/cfg'
xpk_deployment_dir = '/deployment'
gcluster_deploy_command = 'gcluster deploy'
gcluster_create_command = 'gcluster create'
gcluster_destroy_command = 'gcluster destroy'
blueprint_file_name = 'xpk_blueprint.yaml'
deployment_module = '/out/xpk-deployment'
a3_utils_dir_name = 'xpk-gke-a3-megagpu-files'
config_map_repo_path = (
    'src/xpk/blueprints/xpk-gke-a3-megagpu-files/config-map.yaml.tftpl'
)
kueue_config_repo_path = 'src/xpk/blueprints/xpk-gke-a3-megagpu-files/kueue-xpk-configuration.yaml.tftpl'


class CtkManager:
  """CtkManager is a class responsible for running cluster toolkit commands.
  Attributes:
    - deployment_dir (str) : directory containing all files used during building deployment files. It should contain blupeprint file inside:
      deployment_dir:
        - blueprint.yaml
        - dir_used_in_blueprint
    - ctk_cmd_runner (CtkCommandRunner) : instance of class implementing CtkCommandRunner abstract methods.
  Methods:
    - deploy : run a deployment process of cluster toolkit. This method will invoke gcluster create and than gcluster deploy commands.
    - destroy_deployment : run gcluster command to destroy existing deployment.
  """

  def __init__(
      self,
      deployment_dir: str,
      ctk_cmd_runner: CtkCommandRunner,
      deployment_name: str,
      deployment_type: str,
  ) -> None:
    self.deployment_dir = deployment_dir
    self.ctk_cmd_runner = ctk_cmd_runner
    self.deployment_type = deployment_type
    self._prepare_deployment_dir()
    self._blueprint_path = os.path.join(
        self.deployment_dir, blueprint_file_name
    )
    self.deployment_name = deployment_name

  def _prepare_deployment_dir(self) -> None:
    """prepare deployment directory"""

    if not os.path.exists(self.deployment_dir):
      os.makedirs(self.deployment_dir)
      xpk_print(f'Deployment files will be saved to {self.deployment_dir}')
    else:
      xpk_print(
          f'{self.deployment_dir} already exists. Will not override existing'
          ' deployment dir.'
      )

  def _run_create_deployment_cmd(self):
    xpk_print('Creating deployment directory')
    blueprint_container_path = os.path.join('/out', blueprint_file_name)
    cluster_create_cmd = f'{gcluster_create_command} {blueprint_container_path}'
    self.ctk_cmd_runner.run_command(cluster_create_cmd)

  def _run_deploy_cmd(self, auto_approve, dry_run):
    xpk_print('Deploying created resources to cloud.')
    deploy_cmd = f'{gcluster_deploy_command} {self.deployment_name}'
    if auto_approve is True:
      deploy_cmd += ' --auto-approve'
    if dry_run is True:
      return
    self.ctk_cmd_runner.run_command(deploy_cmd)

  def deploy(self, auto_approve=True, dry_run=False) -> None:
    self._run_create_deployment_cmd()
    self._run_deploy_cmd(auto_approve, dry_run)

  def _run_destroy_command(self, auto_approve=True, dry_run=False):
    destroy_cmd = f'{gcluster_destroy_command} {self.deployment_name}'
    if auto_approve is True:
      destroy_cmd += ' --auto-approve'
    if dry_run is True:
      xpk_print(f'executing command {destroy_cmd}')
    self.ctk_cmd_runner.run_command(destroy_cmd)

  def destroy_deployment(self) -> None:
    self._run_destroy_command()

  def _stage_a3_files(self):
    blueprint_utils_dir = os.path.join(self.deployment_dir, a3_utils_dir_name)
    if not os.path.exists(blueprint_utils_dir):
      os.mkdir(blueprint_utils_dir)
    config_map_deploy_path = os.path.join(
        blueprint_utils_dir, 'config-map.yaml.tftpl'
    )
    kueue_configuration_deploy_path = os.path.join(
        blueprint_utils_dir, 'kueue-xpk-configuration.yaml.tftpl'
    )
    shutil.copy(
        config_map_repo_path,
        config_map_deploy_path,
    )
    shutil.copy(
        kueue_config_repo_path,
        kueue_configuration_deploy_path,
    )

  def stage_files(self) -> None:
    """Download files neccessary for deployment to deployment directory."""
    if self.deployment_type == 'a3':
      self._stage_a3_files()
