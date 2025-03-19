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

import subprocess
import sys
from dataclasses import dataclass

from google.api_core.exceptions import PermissionDenied
from google.cloud import resourcemanager_v3
from typing import Optional

from ..parser.args import GlobalConfig
from ..utils.console import xpk_exit, xpk_print
from .commands import run_command_for_value


class GcloudConfig(GlobalConfig):
  """Class representing gcloud project config"""

  gke_version: Optional[str] = None

  @property
  def zone(self) -> str:
    if self._zone is None:
      self._zone = get_zone()
      if self._project is None:
        self._project = get_project()
      xpk_print(f'Working on {self._project} and {self._zone}')
    return self._zone

  @zone.setter
  def zone(self, value: str):
    self._zone = value

  @property
  def region(self):
    return zone_to_region(self.zone)

  @property
  def project(self) -> str:
    if self._project is None:
      self._project = get_project()
      if self._zone is None:
        self._zone = get_zone()
      xpk_print(f'Working on {self._project} and {self._zone}')
    return self._project

  @project.setter
  def project(self, value: str):
    self._project = value

  @property
  def project_number(self) -> str:
    if self._project_number is None:
      client = resourcemanager_v3.ProjectsClient()
      request = resourcemanager_v3.GetProjectRequest()
      request.name = f'projects/{self.project}'
      try:
        response = client.get_project(request=request)
      except PermissionDenied as e:
        xpk_print(
            f"Couldn't translate project id: {self.project} to project number."
            f' Error: {e}'
        )
        xpk_exit(1)
      parts = response.name.split('/', 1)
      xpk_print(f'Project number for project: {self.project} is {parts[1]}')
      self._project_number = str(parts[1])
    return self._project_number

  @project_number.setter
  def project_number(self, value: str):
    self._project_number = value


def get_project():
  """Get GCE project from `gcloud config get project`.

  Returns:
     The project name.
  """
  completed_command = subprocess.run(
      ['gcloud', 'config', 'get', 'project'], check=True, capture_output=True
  )
  project_outputs = completed_command.stdout.decode().strip().split('\n')
  if len(project_outputs) < 1 or project_outputs[-1] == '':
    sys.exit(
        'You must specify the project in the project flag or set it with'
        " 'gcloud config set project <project>'"
    )
  return project_outputs[
      -1
  ]  # The project name lives on the last line of the output


def get_zone():
  """Get GCE zone from `gcloud config get compute/zone`.

  Returns:
     The zone name.
  """
  completed_command = subprocess.run(
      ['gcloud', 'config', 'get', 'compute/zone'],
      check=True,
      capture_output=True,
  )
  zone_outputs = completed_command.stdout.decode().strip().split('\n')
  if len(zone_outputs) < 1 or zone_outputs[-1] == '':
    sys.exit(
        "You must specify the zone in the zone flag or set it with 'gcloud"
        " config set compute/zone <zone>'"
    )
  return zone_outputs[-1]  # The zone name lives on the last line of the output


# TODO: remove when we stop using Namespaces as args
def add_zone_and_project(args: GcloudConfig):
  """Obtains the zone and project names from gcloud configs if not defined.

  Args:
    args: user provided arguments for running the command.
  """
  if not args.project:
    args.project = get_project()
  if not args.zone:
    args.zone = get_zone()
  xpk_print(f'Working on {args.project} and {args.zone}')


def zone_to_region(zone: str) -> str:
  """Helper function converts zone name to region name.

  Args:
    zone: zone name.

  Returns:
     The region name.
  """
  zone_terms = zone.split('-')
  return zone_terms[0] + '-' + zone_terms[1]  # pytype: disable=bad-return-type


@dataclass
class GkeServerConfig:
  """Stores the valid gke versions based on gcloud recommendations."""

  default_rapid_gke_version: str
  valid_versions: set[str]


def get_gke_server_config(
    args: GcloudConfig,
) -> tuple[int, GkeServerConfig | None]:
  """Determine the GKE versions supported by gcloud currently.

  Args:
    args: user provided arguments for running the command.

  Returns:
    Tuple of
    int: 0 if successful and 1 otherwise.
    GkeServerConfig: stores valid gke version to use in node pool and cluster.
  """
  base_command = (
      'gcloud container get-server-config'
      f' --project={args.project} --region={zone_to_region(args.zone)}'
  )
  default_rapid_gke_version_cmd = (
      base_command
      + ' --flatten="channels" --filter="channels.channel=RAPID"'
      ' --format="value(channels.defaultVersion)"'
  )
  valid_versions_cmd = (
      base_command
      + ' --flatten="channels" --filter="channels.channel=RAPID"'
      ' --format="value(channels.validVersions)"'
  )
  base_command_description = 'Determine server supported GKE versions for '

  server_config_commands_and_descriptions = [
      (
          default_rapid_gke_version_cmd,
          base_command_description + 'default rapid gke version',
      ),
      (
          valid_versions_cmd,
          base_command_description + 'valid versions',
      ),
  ]
  command_outputs = []

  for command, command_description in server_config_commands_and_descriptions:
    return_code, cmd_output = run_command_for_value(
        command,
        command_description,
        args,
        hide_error=True,
    )
    if return_code != 0:
      xpk_print(f'Unable to get server config for {command_description}.')
      return return_code, None
    command_outputs.append(cmd_output)

  return 0, GkeServerConfig(
      default_rapid_gke_version=command_outputs[0].strip(),
      valid_versions=set(command_outputs[1].split(';')),
  )


def get_gke_control_plane_version(
    args: GcloudConfig, gke_server_config: GkeServerConfig
) -> tuple[int, str | None]:
  """Determine gke control plane version for cluster creation.

  Args:
    args: user provided arguments for running the command.
    gke_server_config: holds valid gke versions and recommended default version.

  Returns:
    Tuple of
    int: 0 if successful and 1 otherwise.
    str: gke control plane version to use.
  """

  # Override with user provide gke version if specified.
  if args.gke_version is not None:
    master_gke_version = args.gke_version
  else:
    master_gke_version = gke_server_config.default_rapid_gke_version

  is_valid_version = master_gke_version in gke_server_config.valid_versions

  if not is_valid_version:
    xpk_print(
        f'Planned GKE Version: {master_gke_version}\n Valid Versions:'
        f'\n{gke_server_config.valid_versions}\nRecommended / Default GKE'
        f' Version: {gke_server_config.default_rapid_gke_version}'
    )
    xpk_print(
        f'Error: Planned GKE Version {master_gke_version} is not valid.'
        f'Checks failed: Is Version Valid: {is_valid_version}'
    )
    xpk_print(
        'Please select a gke version from the above list using --gke-version=x'
        ' argument or rely on the default gke version:'
        f' {gke_server_config.default_rapid_gke_version}'
    )
    return 1, None

  return 0, master_gke_version
