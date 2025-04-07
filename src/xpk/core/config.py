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
import re

import ruamel.yaml

from ..utils import file
from ..utils.console import xpk_print
from .system_characteristics import AcceleratorType, SystemCharacteristics

# This is the version for XPK PyPI package
__version__ = 'v0.7.2'
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
DEPENDENCIES_KEY = 'deps-verified-version'
XPK_CONFIG_FILE = os.path.expanduser('~/.config/xpk/config.yaml')

DEFAULT_KEYS = [
    CFG_BUCKET_KEY,
    CLUSTER_NAME_KEY,
    PROJECT_KEY,
    ZONE_KEY,
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

    config_yaml = {'version': 'v1', CONFIGS_KEY: {}}
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
  ) -> dict[str, dict[str, str] | str] | None:
    config_yaml = self._open_configs()
    if config_yaml is None:
      return None
    val: dict[str, str] = config_yaml[CONFIGS_KEY]
    return val


def parse_env_config(args, tensorboard_config, system: SystemCharacteristics):
  """Parses the environment configurations to the jobset config.

  Args:
    args: user provided arguments for running the command.
    tensorboard_config: configuration of Vertex Tensorboard.
    system: system characteristics.
  """
  env = {}

  env_pat = re.compile(r'(^[a-zA-Z_][a-zA-Z0-9_]*?)(?:=(.*))?$', re.M)
  if args.env_file:
    print('Setting container environment from', args.env_file)
    with open(file=args.env_file, mode='r', encoding='utf-8') as f:
      for match in env_pat.finditer(f.read()):
        variable = match.group(1)
        if match.group(2) is not None:
          env[variable] = match.group(2)
        else:
          assert variable in os.environ, (
              f'Variable {variable} is not set in the current '
              'environment, a value must be specified.'
          )
          env[variable] = os.environ[variable]
  if args.env:
    for var in args.env:
      match = env_pat.match(var)
      assert match and match.group(2) is not None, (
          'Invalid environment variable, format must be '
          f'`--env VARIABLE=value`: {var}'
      )
      variable = match.group(1)
      env[variable] = match.group(2)

  if not args.use_pathways:
    if args.debug_dump_gcs:
      if 'XLA_FLAGS' in env:
        raise ValueError(
            'Conflict: XLA_FLAGS defined in both --debug_dump_gcs '
            'and environment file. Please choose one way to define '
            'XLA_FLAGS.'
        )
      env['XLA_FLAGS'] = '--xla_dump_to=/tmp/xla_dump/'

    if tensorboard_config:
      env['UPLOAD_DATA_TO_TENSORBOARD'] = True
      for key, value in tensorboard_config.items():
        env[key.upper()] = value

  if system.accelerator_type == AcceleratorType['GPU']:
    # For GPUs, it has two more spaces ahead of name and value respectively
    env_format = '''
                  - name: {key}
                    value: "{value}"'''
  else:
    env_format = '''
                - name: {key}
                  value: "{value}"'''

  args.env = ''.join(env_format.format(key=k, value=v) for k, v in env.items())
