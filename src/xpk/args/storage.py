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

from typing import Optional, Literal, TypeAlias
from .cluster import ClusterConfig


StorageType: TypeAlias = Literal[
    'gcsfuse', 'gcpfilestore', 'parallelstore', 'pd'
]

StorageAccessMode: TypeAlias = Literal[
    'ReadWriteOnce', 'ReadOnlyMany', 'ReadWriteMany'
]

FilestoreTier: TypeAlias = Literal[
    'BASIC_HDD', 'BASIC_SSD', 'ZONAL', 'REGIONAL', 'ENTERPRISE'
]


class StorageAttachArgs(ClusterConfig):
  """Class representing storage attach args type"""
  name: str = None
  type: StorageType = None
  auto_mount: bool = None
  mount_point: str = None
  readonly: bool = None
  size: Optional[int] = None
  bucket: Optional[str] = None
  vol: Optional[str] = None
  access_mode: StorageAccessMode = 'ReadWriteMany'
  instance: Optional[str] = None
  prefetch_metadata: bool = True
  manifest: Optional[str] = None
  mount_options: Optional[str] = 'implicit-dirs'


class StorageCreateArgs(ClusterConfig):
  """Class representing storage create args type"""
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
  manifest: Optional[str] = None


class StorageDeleteArgs(ClusterConfig):
  """Class representing storage delete args type"""
  name: str = None
  force: Optional[bool] = False


class StorageDetachArgs(ClusterConfig):
  """Class representing storage detach args type"""
  name: str = None


class StorageListArgs(ClusterConfig):
  """Class representing storage list args type"""
  pass
