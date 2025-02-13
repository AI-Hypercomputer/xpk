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

from ..utils.console import xpk_print
from .commands import run_command_for_value


class GCloudContextManager:
  """Manages GCloud configuration retrieval and GKE version handling."""

  @classmethod
  def get_project(cls) -> str:
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

  @classmethod
  def get_zone(cls) -> str:
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
    return zone_outputs[
        -1
    ]  # The zone name lives on the last line of the output

  @classmethod
  def add_zone_and_project(cls, args):
    """Obtains the zone and project names from gcloud configs if not defined.

    Args:
      args: user provided arguments for running the command.
    """
    if not args.project:
      args.project = cls.get_project()
    if not args.zone:
      args.zone = cls.get_zone()
    xpk_print(f'Working on {args.project} and {args.zone}')

  @staticmethod
  def zone_to_region(zone) -> str:
    """Helper function converts zone name to region name.

    Args:
      zone: zone name.

    Returns:
      The region name.
    """
    zone_terms = zone.split('-')
    return zone_terms[0] + '-' + zone_terms[1]  # pytype: disable=bad-return-type


class GKEVersionManager:
  """Stores the valid gke versions based on gcloud recommendations."""

  def __init__(self, args):
    self.args = args
    self.default_rapid_gke_version = ''
    self.valid_versions = set()
    return_code = self._initialize_gke_versions()
    if return_code != 0:
      raise RuntimeError('Failed to retrieve GKE versions from gcloud')

  def _initialize_gke_versions(self) -> int:
    """Determine the GKE versions supported by gcloud currently.

    Returns:
      int: 0 if successful and 1 otherwise.
    """
    base_command = (
        'gcloud container get-server-config'
        f' --project={self.args.project} --region={GCloudContextManager.zone_to_region(self.args.zone)}'
    )
    commands = [
        (
            base_command
            + ' --flatten="channels" --filter="channels.channel=RAPID"'
            ' --format="value(channels.defaultVersion)"',
            'default rapid GKE version',
        ),
        (
            base_command
            + ' --flatten="channels" --filter="channels.channel=RAPID"'
            ' --format="value(channels.validVersions)"',
            'valid versions',
        ),
    ]

    results = []
    for command, description in commands:
      return_code, cmd_output = run_command_for_value(
          command,
          description,
          self.args,
          hide_error=True,
      )
      if return_code != 0:
        xpk_print(f'Unable to get server config for {description}.')
        return return_code
      results.append(cmd_output)

    self.default_rapid_gke_version = results[0].strip()
    self.valid_versions = set(results[1].split(';'))

    return 0

  def get_gke_control_plane_version(self) -> tuple[int, str | None]:
    """Determine gke control plane version for cluster creation.

    Returns:
      Tuple of
      int: 0 if successful and 1 otherwise.
      str: gke control plane version to use.
    """

    # Override with user provide gke version if specified.
    master_gke_version = (
        self.args.gke_version
        if self.args.gke_version
        else self.default_rapid_gke_version
    )

    if master_gke_version not in self.valid_versions:
      xpk_print(
          f'Planned GKE Version: {master_gke_version}\n Valid Versions:'
          f'\n{self.valid_versions}\nRecommended / Default GKE'
          f' Version: {self.default_rapid_gke_version}'
      )
      xpk_print(
          f'Error: Planned GKE Version {master_gke_version} is not valid.'
          'Checks failed: Is Version Valid: False'
      )
      xpk_print(
          'Please select a gke version from the above list using'
          ' --gke-version=x argument or rely on the default gke version:'
          f' {self.default_rapid_gke_version}'
      )
      return 1, None

    return 0, master_gke_version
