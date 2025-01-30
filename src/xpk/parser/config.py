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

from ..commands.config import (
    config_set,
    config_get,
)

from .common import add_shared_arguments


class ParseDict(argparse.Action):

  def __call__(self, parser, namespace, values, option_string=None):
    d = getattr(namespace, self.dest) or {}

    if values:
      for item in values:
        split_items = item.split('=', 1)
        key = split_items[
            0
        ].strip()  # we remove blanks around keys, as is logical
        value = split_items[1]

        d[key] = value

    setattr(namespace, self.dest, d)


def set_config_parsers(config_parser):
  config_subcommands = config_parser.add_subparsers(
      title='config subcommands',
      dest='xpk_config_subcommands',
      help='`set`, `get`, config',
  )

  # "config set" command parser.
  config_set_parser = config_subcommands.add_parser(
      'set', help='Set a config key.'
  )
  config_get_parser = config_subcommands.add_parser(
      'get', help='Get a config key value'
  )
  config_set_parser_required_arguments = config_set_parser.add_argument_group(
      'config setBuilt-in Arguments',
      'Configure xpk to create a config for you.',
  )

  config_get_parser_required_arguments = config_get_parser.add_argument_group(
      'config Built-in Arguments',
      'Configure xpk to create a config for you.',
  )
  config_set_parser.set_defaults(func=config_set)
  config_get_parser.set_defaults(func=config_get)
