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
from xpk.utils.console import xpk_exit, xpk_print
import os

xpk_gcloud_cfg_path = '~/gcloud/cfg'
xpk_deployment_dir = '/deployment'
gcluster_deploy_command = 'gcluster deploy'
gcluster_create_command = 'gcluster create'
gcluster_destroy_command = 'gcluster destroy'
machine_ip = '10.0.0.0'
blueprint_file_name = 'xpk_blueprint.yaml'
deployment_module = 'xpk-deployment'


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
  ) -> None:
    self.deployment_dir = deployment_dir
    self.ctk_cmd_runner = ctk_cmd_runner
    self._validate_deployment_dir()
    self._blueprint_path = os.path.join(
        self.deployment_dir, blueprint_file_name
    )

  def _validate_deployment_dir(self) -> None:
    """Check if deployment directory contains blueprint.yaml file."""
    is_blueprint = os.path.exists(
        os.path.join(self.deployment_dir, blueprint_file_name)
    )
    if is_blueprint is False:
      xpk_print('Deployment directory does not contains blueprint file')
      xpk_exit(1)

  def _run_create_deployment_cmd(self):
    xpk_print('Creating deployment directory')
    cluster_create_cmd = f'{gcluster_create_command} {self._blueprint_path}'
    self.ctk_cmd_runner.run_command(cluster_create_cmd)

  def _run_deploy_cmd(self):
    xpk_print('Deploying created resources to cloud.')
    deploy_cmd = f'{gcluster_deploy_command} {deployment_module}'
    self.ctk_cmd_runner.run_command(deploy_cmd)

  # create base class for docker run
  # create dry run
  # add stage_files
  # pass file not blueprint
  # blueprint generator should generate directory with blueprint
  def deploy(self) -> None:
    self._run_create_deployment_cmd()
    self._run_deploy_cmd()

  def _run_destroy_command(self):
    destroy_cmd = f'{gcluster_destroy_command} {deployment_module}'
    self.ctk_cmd_runner.run_command(destroy_cmd)

  def destroy_deployment(self) -> None:
    self._run_destroy_command()
