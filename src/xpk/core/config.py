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

from ..utils import file
from ..utils.console import xpk_print

# This is the version for XPK PyPI package
__version__ = 'v0.13.0'
XPK_CURRENT_VERSION = __version__
XPK_CONFIG_FILE = os.path.expanduser('~/.config/xpk/config.yaml')

CONFIGS_KEY = 'configs'
CFG_BUCKET_KEY = 'cluster-state-gcs-bucket'
CLUSTER_NAME_KEY = 'cluster-name'
PROJECT_KEY = 'project-id'
ZONE_KEY = 'zone'
KJOB_BATCH_IMAGE = 'batch-image'
KJOB_BATCH_WORKING_DIRECTORY = 'batch-working-directory'
KJOB_SHELL_IMAGE = 'shell-image'
KJOB_SHELL_INTERACTIVE_COMMAND = 'shell-interactive-command'
KJOB_SHELL_WORKING_DIRECTORY = 'shell-working-directory'
CONFIGS_KEY = 'configs'
GKE_ENDPOINT_KEY = 'gke-endpoint'
DEPENDENCIES_KEY = 'deps-verified-version'
XPK_CONFIG_FILE = os.path.expanduser('~/.config/xpk/config.yaml')

DEFAULT_KEYS = [
    CFG_BUCKET_KEY,
    CLUSTER_NAME_KEY,
    PROJECT_KEY,
    ZONE_KEY,
    GKE_ENDPOINT_KEY,
    DEPENDENCIES_KEY,
    KJOB_BATCH_IMAGE,
    KJOB_BATCH_WORKING_DIRECTORY,
    KJOB_SHELL_IMAGE,
    KJOB_SHELL_INTERACTIVE_COMMAND,
    KJOB_SHELL_WORKING_DIRECTORY,
]
VERTEX_TENSORBOARD_FEATURE_FLAG = XPK_CURRENT_VERSION >= '0.4.0'


yaml = ruamel.yaml.YAML()


class XpkConfig:
  """XpkConfig is a class for setting and getting values from .yaml config file."""

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

  def set(self, key: str, value: str) -> None:
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
