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

  batch_optional_arguments.add_argument(
      '--ignore-unknown-flags',
      type=bool,
      action=argparse.BooleanOptionalAction,
      default=False,
      help='Ignore all the unsupported flags in the bash script.',
  )
  batch_optional_arguments.add_argument(
      '-a',
      '--array',
      type=str,
      default=None,
      help=(
          'Submit a job array, multiple jobs to be executed with identical'
          ' parameters. The indexes specification identifies what array index'
          ' values should be used. For example, "--array=0-15" or'
          ' "--array=0,6,16-32". Multiple values may be specified using a comma'
          ' separated list and/or a range of values with a "-" separator. For'
          ' example "--array=0-15%%4" will limit the number of simultaneously'
          ' running tasks from this job array to 4. The minimum index value is'
          ' 0. The maximum index value is 2147483647.'
      ),
  )
  batch_optional_arguments.add_argument(
      '-c',
      '--cpus-per-task',
      type=str,
      default=None,
      help='How much cpus a container inside a pod requires.',
  )
  batch_optional_arguments.add_argument(
      '--gpus-per-task',
      type=str,
      default=None,
      help='How much gpus a container inside a pod requires.',
  )
  batch_optional_arguments.add_argument(
      '--mem',
      type=str,
      default=None,
      help='How much memory a pod requires.',
  )
  batch_optional_arguments.add_argument(
      '--mem-per-task',
      type=str,
      default=None,
      help='How much memory a container requires.',
  )
  batch_optional_arguments.add_argument(
      '--mem-per-cpu',
      type=str,
      default=None,
      help=(
          'How much memory a container requires, it multiplies the number '
          'of requested cpus per task by mem-per-cpu.'
      ),
  )
  batch_optional_arguments.add_argument(
      '--mem-per-gpu',
      type=str,
      default=None,
      help=(
          'How much memory a container requires, it multiplies the number '
          'of requested gpus per task by mem-per-gpu.'
      ),
  )
  batch_optional_arguments.add_argument(
      '-N',
      '--nodes',
      type=int,
      default=None,
      help='Number of pods to be used at a time.',
  )
  batch_optional_arguments.add_argument(
      '-n',
      '--ntasks',
      type=int,
      default=None,
      help='Number of identical containers inside of a pod, usually 1.',
  )
  batch_optional_arguments.add_argument(
      '-o',
      '--output',
      type=str,
      default=None,
      help=(
          'Where to redirect the standard output stream of a task. If not'
          ' passed it proceeds to stdout, and is available via kubectl logs.'
      ),
  )
  batch_optional_arguments.add_argument(
      '-e',
      '--error',
      type=str,
      default=None,
      help=(
          'Where to redirect std error stream of a task. If not passed it'
          ' proceeds to stdout, and is available via kubectl logs.'
      ),
  )
  batch_optional_arguments.add_argument(
      '--input',
      type=str,
      default=None,
      help='What to pipe into the script.',
  )
  batch_optional_arguments.add_argument(
      '-J',
      '--job-name',
      type=str,
      default=None,
      help='What is the job name.',
  )
  batch_optional_arguments.add_argument(
      '-D',
      '--chdir',
      type=str,
      default=None,
      help='Change directory before executing the script.',
  )
  batch_optional_arguments.add_argument(
      '-t',
      '--time',
      type=str,
      default=None,
      help=(
          'Set a limit on the total run time of the job. '
          'A time limit of zero requests that no time limit be imposed. '
          'Acceptable time formats include "minutes", "minutes:seconds", '
          '"hours:minutes:seconds", "days-hours", "days-hours:minutes" '
          'and "days-hours:minutes:seconds".'
      ),
  )
