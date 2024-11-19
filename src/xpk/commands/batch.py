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

from argparse import Namespace
from ..utils.console import xpk_exit, xpk_print
from .cluster import set_cluster_command
from ..core.core import add_zone_and_project
from ..core.job_template import create_job_template_instance
from ..core.app_profile import create_app_profile_instance
from ..core.app_profile import APP_PROFILE_TEMPLATE_DEFAULT_NAME
from ..core.commands import (
    run_command_for_value,
    run_command_with_updates,
)


def batch(args: Namespace) -> None:
  """Run batch task.
     This function runs passed script in non-blocking manner.
  Args:
    args: user provided arguments for running the command.
  Returns:
    None
  """
  if not args.kind_cluster:
    add_zone_and_project(args)
    set_cluster_command_code = set_cluster_command(args)
  else:
    set_cluster_command_code = set_local_cluster_command(args)

  if set_cluster_command_code != 0:
    xpk_exit(set_cluster_command_code)

  create_job_template_instance(args)
  create_app_profile_instance(args)
  submit_job(args)


def submit_job(args: Namespace) -> None:
  cmd = (
      'kubectl-kjob create slurm --profile'
      f' {APP_PROFILE_TEMPLATE_DEFAULT_NAME} --'
      f' {args.script}'
  )

  return_code, _ = run_command_for_value(cmd, 'submit job', args)

  if return_code != 0:
    xpk_print(f'Running batch job returned ERROR {return_code}')
    xpk_exit(return_code)


def set_local_cluster_command(args) -> int:
  """Run local cluster configuration command to set the kubectl config.

  Args:
    args: user provided arguments for running the command.

  Returns:
    0 if successful and 1 otherwise.
  """
  if not args.cluster:
    command = 'kubectl config current-context'
    return_code, current_context = run_command_for_value(
        command, 'get current-context', args
    )
    xpk_print(
        'No local cluster name specified. Using current-context'
        f' `{current_context.strip()}`'
    )
    return return_code

  command = (
      f'kubectl config use-context kind-{args.cluster} --namespace=default'
  )
  task = f'switch to cluster {args.cluster}'
  return_code = run_command_with_updates(
      command,
      task,
      args,
  )
  if return_code != 0:
    xpk_print(f'{task} returned ERROR {return_code}')
  return return_code
