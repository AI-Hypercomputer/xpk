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

from ..commands.inspector import inspector
from .validators import name_type
from .common import add_shared_arguments


def set_inspector_parser(inspector_parser):
  inspector_parser.add_subparsers(
      title='inspector subcommands',
      dest='xpk_inspector_subcommands',
      help='Investigate workload, and Kueue failures.',
  )

  inspector_parser_required_arguments = inspector_parser.add_argument_group(
      'inspector Built-in Arguments', 'Arguments required for `inspector`.'
  )
  inspector_parser_optional_arguments = inspector_parser.add_argument_group(
      'Optional Arguments', 'Arguments optional for `inspector`.'
  )

  ### "inspector" Required arguments

  inspector_parser_required_arguments.add_argument(
      '--cluster',
      type=name_type,
      default=None,
      help='The name of the cluster to investigate.',
      required=True,
  )

  ### "inspector" Optional Arguments
  add_shared_arguments(inspector_parser_optional_arguments)

  inspector_parser_optional_arguments.add_argument(
      '--workload',
      type=name_type,
      default=None,
      help='The name of the workload to investigate.',
  )

  inspector_parser_optional_arguments.add_argument(
      '--print-to-terminal',
      action='store_true',
      help=(
          'Prints inspector output to terminal. A user can always look at the'
          ' returned file.'
      ),
  )

  inspector_parser.set_defaults(func=inspector)
