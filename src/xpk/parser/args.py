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

import inspect
from argparse import Namespace
from typing import Any, Optional, Literal

from ..core.gcloud_context import get_project, get_zone, zone_to_region
from ..utils.console import xpk_print


class GlobalArgs:
  """Class representing global args type"""

  dry_run: bool = False


class KindClusterArgs:
  """Class representing kind cluster args type"""

  kind_cluster: bool = False


class ClusterArgs:
  """Class representing cluster args type"""

  cluster: str = None


class SlurmArgs:
  """Class representing slurm args type"""

  ignore_unknown_flags: bool = False
  array: Optional[str] = None
  cpus_per_task: Optional[str] = None
  gpus_per_task: Optional[str] = None
  mem: Optional[str] = None
  mem_per_task: Optional[str] = None
  mem_per_cpu: Optional[str] = None
  mem_per_gpu: Optional[str] = None
  nodes: Optional[int] = None
  ntasks: Optional[int] = None
  output: Optional[str] = None
  error: Optional[str] = None
  input: Optional[str] = None
  job_name: Optional[str] = None
  chdir: Optional[str] = None
  time: Optional[str] = None


class SharedArgs(GlobalArgs):
  """Class representing shared args type"""

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


def apply_args(main_args: Namespace, annotation: Any):
  args = annotation()
  for param in inspect.get_annotations(annotation):
    if param in main_args:
      setattr(args, param, getattr(main_args, param))

  for param, _ in inspect.getmembers(annotation):
    if param in main_args:
      setattr(args, param, getattr(main_args, param))

  return args


### Storage args


class StorageDeleteArgs(SharedArgs, ClusterArgs):
  name: str = None
  force: Optional[bool] = False


class StorageListArgs(SharedArgs, ClusterArgs):
  pass


class StorageDetachArgs(SharedArgs, ClusterArgs, KindClusterArgs):
  name: str = None


StorageAccessMode = Literal['ReadWriteOnce', 'ReadOnlyMany', 'ReadWriteMany']

FilestoreTier = Literal[
    'BASIC_HDD', 'BASIC_SSD', 'ZONAL', 'REGIONAL', 'ENTERPRISE'
]


class StorageAttachArgs(SharedArgs, ClusterArgs, KindClusterArgs):
  name: str = None
  type: Literal['gcsfuse', 'gcpfilestore'] = None
  auto_mount: bool = None
  mount_point: str = None
  readonly: bool = None
  size: Optional[int] = None
  bucket: Optional[str] = None
  vol: Optional[str] = None
  access_mode: StorageAccessMode = 'ReadWriteMany'
  instance: Optional[str] = None


class StorageCreateArgs(SharedArgs, ClusterArgs, KindClusterArgs):
  name: str = None
  access_mode: StorageAccessMode = 'ReadWriteMany'
  vol: str = 'default'
  size: int = None
  tier: FilestoreTier = 'BASIC_HDD'
  type: Literal['gcpfilestore'] = 'gcpfilestore'
  auto_mount: bool = None
  mount_point: str = None
  readonly: bool = None
  instance: Optional[str] = None
