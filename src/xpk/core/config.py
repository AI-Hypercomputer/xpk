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

import ruamel.yaml
import os

from ..utils import file
from ..utils.console import xpk_print

CFG_BUCKET_KEY = 'cluster-state-gcs-bucket'
CLUSTER_NAME_KEY = 'cluster-name'
PROJECT_KEY = 'project-id'
ZONE_KEY = 'zone'
CONFIG_PATH = '~/.config/xpk/config.yaml'
CONFIGS_KEY = 'configs'

default_keys = [
    CFG_BUCKET_KEY,
    CLUSTER_NAME_KEY,
    PROJECT_KEY,
    ZONE_KEY,
]

yaml = ruamel.yaml.YAML()


class XpkConfig:
  """XpkConfig is a class for setting and getting values from .yaml config file."""

  def __init__(self, config_file_path: str = CONFIG_PATH) -> None:
    self._config = config_file_path
    self._allowed_keys = default_keys

  def _open_configs(self) -> dict:
    config_yaml: dict = {}
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

    dir_path = '/'.join(self._config.split('/')[:-1])
    file.ensure_directory_exists(dir_path)

    config_yaml = {'version': 'v1', CONFIGS_KEY: {}}
    if os.path.exists(self._config):
      config_yaml = self._open_configs()

    config_yaml[CONFIGS_KEY][key] = value
    self._save_configs(config_yaml)

  def get(self, key: str) -> str | None:
    if key not in self._allowed_keys:
      xpk_print(f'Key {key} is not an allowed xpk config key.')
      return None

    if not os.path.exists(self._config):
      return None

    config_yaml = self._open_configs()
    vals: dict[str, str] = config_yaml[CONFIGS_KEY]
    return vals[key]

  def get_all(
      self,
  ) -> dict[str, dict[str, str] | str]:
    if not os.path.exists(self._config):
      return {}
    config_yaml = self._open_configs()
    return config_yaml
