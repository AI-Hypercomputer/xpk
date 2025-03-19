from typing import Optional, Literal
from ...core.cluster import ClusterConfig


StorageAccessMode = Literal['ReadWriteOnce', 'ReadOnlyMany', 'ReadWriteMany']

FilestoreTier = Literal[
    'BASIC_HDD', 'BASIC_SSD', 'ZONAL', 'REGIONAL', 'ENTERPRISE'
]


class StorageAttachArgs(ClusterConfig):
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


class StorageCreateArgs(ClusterConfig):
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


class StorageDeleteArgs(ClusterConfig):
  name: str = None
  force: Optional[bool] = False


class StorageDetachArgs(ClusterConfig):
  name: str = None


class StorageListArgs(ClusterConfig):
  pass
