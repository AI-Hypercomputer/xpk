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
from ..commands.job import job_list, job_cancel


def set_job_parser(job_parser):
  job_subcommands = job_parser.add_subparsers(
      title='job subcommands',
      dest='xpk_job_subcommands',
      help=(
          'These are commands related to job management. Look at help for'
          ' specific subcommands for more details.'
      ),
  )

  ### "job ls" command parser ###
  job_list_parser = job_subcommands.add_parser('ls', help='List jobs.')

  job_list_required_arguments = job_list_parser.add_argument_group(
      'Required Arguments',
      'Arguments required for job list.',
  )
  job_list_optional_arguments = job_list_parser.add_argument_group(
      'Optional Arguments', 'Arguments optional for job list.'
  )

  ### Required arguments
  job_list_required_arguments.add_argument(
      '--cluster',
      type=str,
      default=None,
      help='The name of the cluster to list jobs on.',
      required=True,
  )

  job_list_optional_arguments.add_argument(
      '--kind-cluster',
      type=bool,
      action=argparse.BooleanOptionalAction,
      default=False,
      help='Apply command to a local test cluster.',
  )

  add_shared_arguments(job_list_optional_arguments)
  job_list_parser.set_defaults(func=job_list)

  ### "job cancel" command parser ###
  job_cancel_parser = job_subcommands.add_parser(
      'cancel', help='Cancel job execution.'
  )

  job_cancel_required_arguments = job_cancel_parser.add_argument_group(
      'Required Arguments',
      'Arguments required for job cancel.',
  )
  job_cancel_optional_arguments = job_cancel_parser.add_argument_group(
      'Optional Arguments', 'Arguments optional for job cancel.'
  )

  ### Required arguments
  job_cancel_required_arguments.add_argument(
      'name',
      type=str,
      default=None,
      help='The name of the job to be cancelled.',
      nargs='+',
  )

  job_cancel_required_arguments.add_argument(
      '--cluster',
      type=str,
      default=None,
      help='The name of the cluster to delete the job on.',
      required=True,
  )

  job_cancel_optional_arguments.add_argument(
      '--kind-cluster',
      type=bool,
      action=argparse.BooleanOptionalAction,
      default=False,
      help='Apply command to a local test cluster.',
  )

  add_shared_arguments(job_cancel_optional_arguments)
  job_cancel_parser.set_defaults(func=job_cancel)
