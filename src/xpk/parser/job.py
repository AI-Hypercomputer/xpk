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

from .common import add_shared_arguments
from ..commands.job import job_list


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
  job_list_parser = job_subcommands.add_parser('ls', help='List Slurm jobs.')

  add_shared_arguments(job_list_parser)
  job_list_parser.set_defaults(func=job_list)