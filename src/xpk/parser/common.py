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


def add_shared_arguments(
    custom_parser: argparse.ArgumentParser, required=False
) -> None:
  """Add shared arguments to the parser.

  Args:
    custom_parser: parser to add shared arguments to.
  """
  custom_parser.add_argument(
      '--project',
      type=str,
      default=None,
      help='GCE project name, defaults to "gcloud config project."',
      required=required,
  )
  custom_parser.add_argument(
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
  custom_parser.add_argument(
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


def add_cluster_arguments(
    custom_parser: argparse.ArgumentParser, required=False
) -> None:
  """Add cluster argument to the parser.

  Args:
    custom_parser: parser to add shared arguments to.
  """
  custom_parser.add_argument(
      '--cluster',
      type=str,
      default=None,
      help='The name of the cluster.',
      required=required,
  )


def add_kind_cluster_arguments(custom_parser: argparse.ArgumentParser) -> None:
  """Add kind cluster arguments to the parser.

  Args:
    custom_parser: parser to add shared arguments to.
  """
  custom_parser.add_argument(
      '--kind-cluster',
      type=bool,
      action=argparse.BooleanOptionalAction,
      default=False,
      help='Apply command to a local test cluster.',
  )


def add_global_arguments(custom_parser: argparse.ArgumentParser):
  """Add global - no cloud dependent -  arguments to the parser.

  Args:
    custom_parser: parser to add global arguments to.
  """
  custom_parser.add_argument(
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


def add_slurm_arguments(custom_parser: argparse.ArgumentParser):
  """Add Slurm job arguments to the parser.

  Args:
    custom_parser: parser to add global arguments to.
  """
  custom_parser.add_argument(
      '--ignore-unknown-flags',
      type=bool,
      action=argparse.BooleanOptionalAction,
      default=False,
      help='Ignore all the unsupported flags in the bash script.',
  )
  custom_parser.add_argument(
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
  custom_parser.add_argument(
      '-c',
      '--cpus-per-task',
      type=str,
      default=None,
      help='How much cpus a container inside a pod requires.',
  )
  custom_parser.add_argument(
      '--gpus-per-task',
      type=str,
      default=None,
      help='How much gpus a container inside a pod requires.',
  )
  custom_parser.add_argument(
      '--mem',
      type=str,
      default=None,
      help='How much memory a pod requires.',
  )
  custom_parser.add_argument(
      '--mem-per-task',
      type=str,
      default=None,
      help='How much memory a container requires.',
  )
  custom_parser.add_argument(
      '--mem-per-cpu',
      type=str,
      default=None,
      help=(
          'How much memory a container requires, it multiplies the number '
          'of requested cpus per task by mem-per-cpu.'
      ),
  )
  custom_parser.add_argument(
      '--mem-per-gpu',
      type=str,
      default=None,
      help=(
          'How much memory a container requires, it multiplies the number '
          'of requested gpus per task by mem-per-gpu.'
      ),
  )
  custom_parser.add_argument(
      '-N',
      '--nodes',
      type=int,
      default=None,
      help='Number of pods to be used at a time.',
  )
  custom_parser.add_argument(
      '-n',
      '--ntasks',
      type=int,
      default=None,
      help='Number of identical containers inside of a pod, usually 1.',
  )
  custom_parser.add_argument(
      '-o',
      '--output',
      type=str,
      default=None,
      help=(
          'Where to redirect the standard output stream of a task. If not'
          ' passed it proceeds to stdout, and is available via kubectl logs.'
      ),
  )
  custom_parser.add_argument(
      '-e',
      '--error',
      type=str,
      default=None,
      help=(
          'Where to redirect std error stream of a task. If not passed it'
          ' proceeds to stdout, and is available via kubectl logs.'
      ),
  )
  custom_parser.add_argument(
      '--input',
      type=str,
      default=None,
      help='What to pipe into the script.',
  )
  custom_parser.add_argument(
      '-J',
      '--job-name',
      type=str,
      default=None,
      help='What is the job name.',
  )
  custom_parser.add_argument(
      '-D',
      '--chdir',
      type=str,
      default=None,
      help='Change directory before executing the script.',
  )
  custom_parser.add_argument(
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
  custom_parser.add_argument(
      '--priority',
      type=str,
      default='medium',
      choices=['very-low', 'low', 'medium', 'high', 'very-high'],
      help=(
          'A priority, one of `very-low`, `low`, `medium`, `high` or'
          ' `very-high`. Defaults to `medium`.'
      ),
  )
