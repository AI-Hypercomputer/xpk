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

import argparse

from .common import add_shared_arguments
from ..commands.batch import batch


def set_batch_parser(batch_parser):
  batch_required_arguments = batch_parser.add_argument_group(
      'batch Built-in Arguments', 'Arguments required for `batch`.'
  )
  batch_optional_arguments = batch_parser.add_argument_group(
      'Optional Arguments', 'Arguments optional for `batch`.'
  )

  ### "batch" Required arguments
  batch_required_arguments.add_argument(
      'script', help='script with batch task to run'
  )
  batch_optional_arguments.add_argument(
      '--cluster',
      type=str,
      default=None,
      help='Cluster to which command applies.',
  )
  batch_optional_arguments.add_argument(
      '--kind-cluster',
      type=bool,
      action=argparse.BooleanOptionalAction,
      default=False,
      help='Apply command to a local test cluster.',
  )
  add_shared_arguments(batch_optional_arguments)

  batch_parser.set_defaults(func=batch)
