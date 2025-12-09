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

import os

import ruamel.yaml
from abc import ABC, abstractmethod
from ..utils import file
from ..utils.console import xpk_print
from setuptools_scm import get_version as setuptools_get_version
from importlib.metadata import version, PackageNotFoundError


def _get_version() -> str:
  xpk_version_override = os.getenv('XPK_VERSION_OVERRIDE', '')
  if xpk_version_override != '':
    return xpk_version_override

  try:
    return setuptools_get_version()
  except LookupError:
    pass

  try:
    return version('xpk')
  except PackageNotFoundError:
    pass

  raise LookupError('unable to determine version number')


__version__ = _get_version()
XPK_CURRENT_VERSION = __version__
XPK_CONFIG_FILE = os.path.expanduser('~/.config/xpk/config.yaml')

CONFIGS_KEY = 'configs'
CFG_BUCKET_KEY = 'cluster-state-gcs-bucket'
CLUSTER_NAME_KEY = 'cluster-name'
PROJECT_KEY = 'project-id'
CLIENT_ID_KEY = 'client-id'
SEND_TELEMETRY_KEY = 'send-telemetry'
ZONE_KEY = 'zone'

DEFAULT_KEYS = [
    CFG_BUCKET_KEY,
    CLUSTER_NAME_KEY,
    PROJECT_KEY,
    CLIENT_ID_KEY,
    SEND_TELEMETRY_KEY,
    ZONE_KEY,
]
VERTEX_TENSORBOARD_FEATURE_FLAG = XPK_CURRENT_VERSION >= '0.4.0'


yaml = ruamel.yaml.YAML()


class Config(ABC):
  """Stores and manipulates XPK configuration."""

  @abstractmethod
  def set(self, key: str, value: str | None) -> None:
    """Sets the config value"""
    pass

  @abstractmethod
  def get(self, key: str) -> str | None:
    """Reads the config value"""
    pass

  @abstractmethod
  def get_all(
      self,
  ) -> dict[str, str] | None:
    pass


class FileSystemConfig(Config):
  """XPK Configuration manipulation class leveraging the file system."""

  def __init__(self, custom_config_file: str = XPK_CONFIG_FILE) -> None:
    self._config = custom_config_file
    self._allowed_keys = DEFAULT_KEYS

  def _open_configs(self) -> dict | None:
    dir_path = '/'.join(self._config.split('/')[:-1])
    file.ensure_directory_exists(dir_path)

    if not os.path.exists(self._config):
      return None

    with open(self._config, encoding='utf-8', mode='r') as stream:
      config_yaml: dict = yaml.load(stream)
      return config_yaml

  def _save_configs(self, config_yaml: dict) -> None:
    with open(self._config, encoding='utf-8', mode='w') as stream:
      yaml.dump(config_yaml, stream)

  def set(self, key: str, value: str | None) -> None:
    if key not in self._allowed_keys:
      xpk_print(f'Key {key} is not an allowed xpk config key.')
      return

    config_yaml = self._open_configs()
    if config_yaml is None:
      config_yaml = {'version': 'v1', CONFIGS_KEY: {}}

    config_yaml[CONFIGS_KEY][key] = value
    self._save_configs(config_yaml)

  def get(self, key: str) -> str | None:
    if key not in self._allowed_keys:
      xpk_print(f'Key {key} is not an allowed xpk config key.')
      return None

    config_yaml = self._open_configs()
    if config_yaml is None:
      return None

    vals: dict[str, str] = config_yaml[CONFIGS_KEY]
    return vals.get(key)

  def get_all(
      self,
  ) -> dict[str, str] | None:
    config_yaml = self._open_configs()
    if config_yaml is None:
      return None
    val: dict[str, str] = config_yaml[CONFIGS_KEY]
    return val


class InMemoryXpkConfig(Config):
  """XPK Configuration manipulation class in memory."""

  def __init__(self) -> None:
    self._config: dict[str, str] = {}
    self._allowed_keys = DEFAULT_KEYS

  def set(self, key: str, value: str | None) -> None:
    if key not in self._allowed_keys:
      return
    if value is None:
      self._config.pop(key, None)
    else:
      self._config[key] = value

  def get(self, key: str) -> str | None:
    if key not in self._allowed_keys:
      return None
    return self._config.get(key)

  def get_all(
      self,
  ) -> dict[str, str] | None:
    return None if len(self._config) <= 0 else self._config


_xpk_config: Config = InMemoryXpkConfig()


def set_config(config: Config):
  global _xpk_config
  _xpk_config = config


def get_config() -> Config:
  return _xpk_config
