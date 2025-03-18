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

from ..commands.config import get_config, set_config
from ..core.config import DEFAULT_KEYS
from .common import add_shared_arguments


def set_config_parsers(config_parser):
  add_shared_arguments(config_parser)

  config_subcommands = config_parser.add_subparsers(
      title='config subcommands', dest='xpk_config_subcommands'
  )
  config_set_parser = config_subcommands.add_parser(
      'set', help='set config key'
  )
  config_get_parser = config_subcommands.add_parser(
      'get', help='get config key'
  )
  config_set_parser.add_argument(
      'set_config_args',
      help=f"""Pair of (key, value) to be set in config. Allowed keys are: {DEFAULT_KEYS}.
      Command usage: `xpk config set key value`""",
      type=str,
      nargs=2,
  )
  config_get_parser.add_argument(
      'get_config_key',
      help=f"""Get key value from config. Allowed keys are: {DEFAULT_KEYS} .
      Command usage: `xpk config get key`""",
      type=str,
      nargs=1,
  )
  config_set_parser.set_defaults(func=set_config)
  config_get_parser.set_defaults(func=get_config)
