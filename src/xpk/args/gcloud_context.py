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

from typing import Optional

from google.api_core.exceptions import PermissionDenied
from google.cloud import resourcemanager_v3

import subprocess
import sys
from ..utils.console import xpk_exit, xpk_print
from .common import GlobalConfig


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


class GcloudConfig(GlobalConfig):
  """Class representing gcloud project config"""

  gke_version: Optional[str] = None

  _zone: Optional[str] = None
  _project: Optional[str] = None
  _project_number: Optional[str] = None

  @property
  def zone(self) -> str:
    if self._zone is None:
      self._zone = get_zone()
      if self._project is None:
        self._project = get_project()
      xpk_print(f'Working on {self._project} and {self._zone}')
    return str(self._zone)

  @zone.setter
  def zone(self, value: str):
    self._zone = value

  @property
  def region(self):
    return '-'.join(self.zone.split('-')[:2])

  @property
  def project(self) -> str:
    if self._project is None:
      self._project = get_project()
      if self._zone is None:
        self._zone = get_zone()
      xpk_print(f'Working on {self._project} and {self._zone}')
    return str(self._project)

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
    return str(self._project_number)

  @project_number.setter
  def project_number(self, value: str):
    self._project_number = value
