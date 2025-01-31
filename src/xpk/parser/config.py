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
    config,
)
import argparse
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
  config_parser.add_subparsers(
      title='config subcommands',
      dest='xpk_config_subcommands',
      help='`set`, `get`, config',
  )
  add_shared_arguments(config_parser)
  config_required_arguments = config_parser.add_argument_group(
      'Required Arguments', 'Arguments required for config.'
  )
  config_args = config_required_arguments.add_mutually_exclusive_group()
  config_args.add_argument(
      '--get',
      type=str,
      default=None,
      help='Show only localqueues resources and usage',
  )
  config_args.add_argument(
      '--set',
      action=ParseDict,
      nargs='+',
      metavar='KEY=VALUE',
      help='Show only localqueues resources and usage',
  )
  config_parser.set_defaults(func=config)
