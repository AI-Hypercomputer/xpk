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

from ..commands.info import info
from .common import add_shared_arguments
from .validators import name_type
import argparse


def set_info_parser(info_parser: argparse.ArgumentParser) -> None:
  info_required_arguments = info_parser.add_argument_group(
      'Required Arguments', 'Arguments required for info.'
  )
  info_optional_arguments = info_parser.add_argument_group(
      'Optional Arguments', 'Arguments optional for info.'
  )

  info_required_arguments.add_argument(
      '--cluster',
      type=name_type,
      default=None,
      help='Cluster to which command applies.',
      required=True,
  )

  info_optional_arguments.add_argument(
      '--namespace',
      type=str,
      default='',
      help='Namespace to which resources and queues belong',
  )

  queues_flitering_group = (
      info_optional_arguments.add_mutually_exclusive_group()
  )

  queues_flitering_group.add_argument(
      '--clusterqueue',
      action='store_true',
      default=None,
      help='Show only clusterqueues resources and usage',
  )

  queues_flitering_group.add_argument(
      '--localqueue',
      action='store_true',
      default=None,
      help='Show only localqueues resources and usage',
  )
  add_shared_arguments(info_optional_arguments)
  info_parser.set_defaults(func=info)
