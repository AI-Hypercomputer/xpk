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
from typing import Protocol, Any
from ..core.system_characteristics import get_system_characteristics_keys_by_accelerator_type, AcceleratorType
import difflib
from argcomplete import ChoicesCompleter
from argparse import Action, ArgumentError


class ParserOrArgumentGroup(Protocol):

  def add_argument(self, *args, **kwargs) -> Any:
    ...


class ManyChoicesAction(Action):
  """An action class to output better error message for arguments with large lists of choices."""

  def __init__(self, *args, large_choice_list, **kwargs):
    self.large_list_of_choices = large_choice_list
    super().__init__(*args, **kwargs)

  def __call__(self, parser, namespace, value, option_string=None):
    if value not in self.large_list_of_choices:
      close_matches = difflib.get_close_matches(
          value, self.large_list_of_choices, n=5, cutoff=0
      )
      msg = (
          f"invalid choice: '{value}' (closest matches:"
          f" {', '.join(close_matches)})"
      )
      raise ArgumentError(self, msg)
    setattr(namespace, self.dest, value)


def add_many_choices_argument(
    parserOrGroup: ParserOrArgumentGroup,
    flag_name,
    choices: list[str],
    metavar: str,
    help_msg: str,
    required: bool = False,
) -> None:
  parserOrGroup.add_argument(
      flag_name,
      action=ManyChoicesAction,
      large_choice_list=choices,
      type=str,
      metavar=metavar,
      help=help_msg,
      required=required,
      default=None,
  ).completer = ChoicesCompleter(choices)


def add_shared_arguments(
    custom_parser_or_group: ParserOrArgumentGroup, required=False
) -> None:
  """Add shared arguments to the parser or argument group.

  Args:
    custom_parser_or_group: parser or argument group to add shared arguments to.
  """
  custom_parser_or_group.add_argument(
      '--project',
      type=str,
      default=None,
      help='GCE project name, defaults to "gcloud config project."',
      required=required,
  )
  custom_parser_or_group.add_argument(
      '--zone',
      type=str,
      default=None,
      help=(
          'GCE zone, e.g. us-central2-b, defaults to "gcloud config '
          'compute/zone." Only one of --zone or --region is allowed in a '
          'command.'
      ),
      required=required,
  )
  custom_parser_or_group.add_argument(
      '--dry-run',
      type=bool,
      action=argparse.BooleanOptionalAction,
      default=False,
      help=(
          'If given `--dry-run`, xpk will print the commands it wants to run'
          ' but not run them. This is imperfect in cases where xpk might'
          ' branch based on the output of commands'
      ),
      required=required,
  )
  custom_parser_or_group.add_argument(
      '--skip-validation',
      type=bool,
      action=argparse.BooleanOptionalAction,
      default=False,
      help=(
          'Skip dependency validation checks (kubectl, gcloud, docker, etc). '
          'Independent of --dry-run.'
      ),
      required=required,
  )
  custom_parser_or_group.add_argument(
      '--quiet',
      type=bool,
      action=argparse.BooleanOptionalAction,
      default=False,
      help='Disables prompting before unintended destructive actions.',
      required=required,
  )


def add_cluster_arguments(
    custom_parser_or_group: ParserOrArgumentGroup, required=False
) -> None:
  """Add cluster argument to the parser or argument group.

  Args:
    custom_parser_or_group: parser or argument group to add shared arguments to.
  """
  custom_parser_or_group.add_argument(
      '--cluster',
      type=str,
      default=None,
      help='The name of the cluster.',
      required=required,
  )


def add_kind_cluster_arguments(
    custom_parser_or_group: ParserOrArgumentGroup,
) -> None:
  """Add kind cluster arguments to the parser or argument group.

  Args:
    custom_parser_or_group: parser or argument group to add shared arguments to.
  """
  custom_parser_or_group.add_argument(
      '--kind-cluster',
      type=bool,
      action=argparse.BooleanOptionalAction,
      default=False,
      help='Apply command to a local test cluster.',
  )


def add_global_arguments(custom_parser_or_group: ParserOrArgumentGroup):
  """Add global - no cloud dependent -  arguments to the parser.

  Args:
    custom_parser_or_group: parser or argument group to add global arguments to.
  """
  custom_parser_or_group.add_argument(
      '--dry-run',
      type=bool,
      action=argparse.BooleanOptionalAction,
      default=False,
      help=(
          'If given `--dry-run`, xpk will print the commands it wants to run'
          ' but not run them. This is imperfect in cases where xpk might'
          ' branch based on the output of commands'
      ),
  )


def add_tpu_type_argument(
    custom_parser_or_group: ParserOrArgumentGroup,
    required: bool = False,
) -> None:
  add_many_choices_argument(
      custom_parser_or_group,
      '--tpu-type',
      choices=get_system_characteristics_keys_by_accelerator_type(
          [AcceleratorType.TPU]
      ),
      metavar='TPU_TYPE',
      help_msg='The tpu type to use, v5litepod-16, etc.',
      required=required,
  )


def add_device_type_argument(
    custom_parser_or_group: ParserOrArgumentGroup,
    required: bool = False,
) -> None:
  add_many_choices_argument(
      custom_parser_or_group,
      '--device-type',
      choices=get_system_characteristics_keys_by_accelerator_type(),
      metavar='DEVICE_TYPE',
      help_msg=(
          'The device type to use (can be tpu or gpu or cpu), v5litepod-16,'
          ' h100-80gb-8, n2-standard-32-4 etc.'
      ),
      required=required,
  )


def add_tpu_and_device_type_arguments(
    custom_parser_or_group: ParserOrArgumentGroup,
) -> None:
  add_tpu_type_argument(custom_parser_or_group)
  add_device_type_argument(custom_parser_or_group)


def extract_command_path(parser: argparse.ArgumentParser, args):
  """
  Reconstructs the command path (e.g. 'cluster create').
  """

  def _get_path_segments(current_parser):
    subparser_action = next(
        (
            action
            for action in current_parser._actions  # pylint: disable=protected-access
            if isinstance(action, argparse._SubParsersAction)  # pylint: disable=protected-access
        ),
        None,
    )

    if subparser_action is None:
      return []

    chosen_command = getattr(args, subparser_action.dest, None)

    if chosen_command is None:
      return []

    if chosen_command in subparser_action.choices:
      next_parser = subparser_action.choices[chosen_command]
      return [chosen_command] + _get_path_segments(next_parser)

    return [chosen_command]

  return ' '.join(_get_path_segments(parser))
