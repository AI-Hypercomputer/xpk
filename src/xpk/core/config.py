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

from xpk.utils.console import xpk_print

CFG_BUCKET_KEY = 'cluster-state-gcs-bucket'
CLUSTER_NAME_KEY = 'cluster-name'
PROJECT_KEY = 'project-id'
ZONE_KEY = 'zone'
default_keys = [
    CFG_BUCKET_KEY,
    CLUSTER_NAME_KEY,
    PROJECT_KEY,
    ZONE_KEY,
]

yaml = ruamel.yaml.YAML()


class XpkConfig:
  """_summary_"""

  def __init__(self, config_file_path: str) -> None:
    self._config = config_file_path
    self._allowed_keys = default_keys

    dir_path = '/'.join(self._config.split('/')[:-1])
    xpk_print(dir_path)
    if not os.path.exists(dir_path):
      os.makedirs(dir_path)

  def set(self, key: str, value: str) -> None:
    if key not in self._allowed_keys:
      xpk_print(f'Key {key} is not an allowed xpk config key.')
      return

    config_yaml = {}
    if os.path.exists(self._config):
      with open(self._config, encoding='utf-8', mode='r') as stream:
        config_yaml = yaml.load(stream)

    config_yaml[key] = value
    with open(self._config, encoding='utf-8', mode='w') as stream:
      yaml.dump(config_yaml, stream)

  def get(self, key: str) -> str:
    if key not in self._allowed_keys:
      xpk_print(f'Key {key} is not an allowed xpk config key.')
      return ''

    if not os.path.exists(self._config):
      return ''

    with open(self._config, encoding='utf-8', mode='r') as stream:
      config_yaml = yaml.load(stream)
      if config_yaml is None or key not in config_yaml:
        xpk_print(f'Key {key} not found in config')
        return ''
      return config_yaml[key]

  def get_all(
      self,
  ) -> dict[str, str]:
    if not os.path.exists(self._config):
      return {}
    with open(self._config, encoding='utf-8', mode='r') as stream:
      config_yaml = yaml.load(stream)
      return config_yaml
