"""
Copyright 2025 Google LLC

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

from ..commands.run import run
from .common import (
    add_shared_arguments,
    add_slurm_arguments,
    add_cluster_arguments,
    add_kind_cluster_arguments,
)


def set_run_parser(run_parser):
  run_required_arguments = run_parser.add_argument_group(
      'Required Arguments', 'Arguments required for `run`.'
  )
  run_optional_arguments = run_parser.add_argument_group(
      'Optional Arguments', 'Arguments optional for `run`.'
  )

  run_required_arguments.add_argument('script', help='script with task to run')
  run_optional_arguments.add_argument(
      '--timeout',
      type=int,
      default=None,
      help='Amount of time to wait for job in seconds',
      required=False,
  )

  add_cluster_arguments(run_optional_arguments)
  add_kind_cluster_arguments(run_optional_arguments)
  add_slurm_arguments(run_optional_arguments)
  add_shared_arguments(run_parser)
  run_parser.set_defaults(func=run)
