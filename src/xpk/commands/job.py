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

from ..utils.console import xpk_exit, xpk_print
from ..core.core import add_zone_and_project
from ..core.kjob import AppProfileDefaults
from ..core.commands import (
    run_command_with_updates,
)
from .cluster import set_cluster_command
from .kind import set_local_cluster_command


def job_list(args) -> None:
  """Function around job list.

  Args:
    args: user provided arguments for running the command.

  Returns:
    None
  """
  if not args.kind_cluster:
    add_zone_and_project(args)
    set_cluster_command_code = set_cluster_command(args)
    msg = f'Listing jobs for project {args.project} and zone {args.zone}:'
  else:
    set_cluster_command_code = set_local_cluster_command(args)
    msg = 'Listing jobs:'

  if set_cluster_command_code != 0:
    xpk_exit(set_cluster_command_code)
  xpk_print(msg, flush=True)

  return_code = run_slurm_job_list_command(args)
  xpk_exit(return_code)


def run_slurm_job_list_command(args) -> int:
  cmd = f'kubectl-kjob list slurm  --profile {AppProfileDefaults.NAME.value}'

  return_code = run_command_with_updates(cmd, 'list jobs', args)
  if return_code != 0:
    xpk_print(f'Listing jobs returned ERROR {return_code}')
  return return_code


def job_cancel(args) -> None:
  """Function around job cancel.

  Args:
    args: user provided arguments for running the command.

  Returns:
    None
  """
  xpk_print(f'Starting job cancel for job: {args.name}', flush=True)
  if not args.kind_cluster:
    add_zone_and_project(args)
    set_cluster_command_code = set_cluster_command(args)
  else:
    set_cluster_command_code = set_local_cluster_command(args)

  if set_cluster_command_code != 0:
    xpk_exit(set_cluster_command_code)

  return_code = run_slurm_job_delete_command(args)
  xpk_exit(return_code)


def run_slurm_job_delete_command(args) -> int:
  list_of_jobs = ' '.join(args.name)
  cmd = f'kubectl-kjob delete slurm {list_of_jobs}'

  return_code = run_command_with_updates(cmd, 'delete job', args)
  if return_code != 0:
    xpk_print(f'Delete job request returned ERROR {return_code}')
  return return_code
