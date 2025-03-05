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

from ..commands.shell import shell, shell_stop
from .common import (
    add_shared_arguments,
    add_cluster_arguments,
    add_kind_cluster_arguments,
)
import argparse


def set_shell_parser(shell_parser: argparse.ArgumentParser) -> None:
  shell_optional_arguments = shell_parser.add_argument_group(
      'Optional Arguments', 'Arguments optional for shell.'
  )
  add_shared_arguments(shell_optional_arguments)
  shell_parser.set_defaults(func=shell)

  add_cluster_arguments(shell_optional_arguments)
  add_kind_cluster_arguments(shell_optional_arguments)

  shell_subcommands = shell_parser.add_subparsers(
      title='shell subcommands',
      dest='xpk_shell_subcommands',
      help=(
          'These are commands related to interactive shell. Look at help for'
          ' specific subcommands for more details.'
      ),
  )

  set_shell_stop_parser(
      shell_stop_parser=shell_subcommands.add_parser(
          name='stop', help='Stop the running shell.'
      )
  )


def set_shell_stop_parser(shell_stop_parser: argparse.ArgumentParser):
  shell_stop_optional_arguments = shell_stop_parser.add_argument_group(
      'Optional Arguments', 'Arguments optional for shell stop.'
  )
  add_shared_arguments(shell_stop_optional_arguments)
  shell_stop_parser.set_defaults(func=shell_stop)
  add_cluster_arguments(shell_stop_parser)
  add_kind_cluster_arguments(shell_stop_optional_arguments)
