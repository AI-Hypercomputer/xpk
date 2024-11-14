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
from ..commands.job import job_info
from .common import add_shared_arguments


def set_job_parser(job_parser: argparse.ArgumentParser):
  job_subcommands = job_parser.add_subparsers(
      title='job subcommands',
      dest='xpk_job_subcommands',
      help='`info` about single specified job.',
  )
  set_job_info_parser(
      job_info_parser=job_subcommands.add_parser(
          'info', help='Show information about specified job.'
      )
  )


def set_job_info_parser(job_info_parser: argparse.ArgumentParser):
  job_info_parser_required_arguments = job_info_parser.add_argument_group(
      'Required arguments',
      'The basic information required to identify the job.',
  )
  job_info_parser_required_arguments.add_argument(
      'name',
      type=str,
      default=None,
      help='Name of the job.',
  )
  job_info_parser.set_defaults(func=job_info)
  add_shared_arguments(job_info_parser)
