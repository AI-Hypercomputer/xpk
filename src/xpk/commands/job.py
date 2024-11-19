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
from ..core.app_profile import APP_PROFILE_TEMPLATE_DEFAULT_NAME
from ..core.commands import (
    run_command_with_updates,
)


def job_list(args) -> None:
  """Function around job list.

  Args:
    args: user provided arguments for running the command.

  Returns:
    None
  """
  add_zone_and_project(args)
  xpk_print(
      f'Listing jobs for project {args.project} and zone {args.zone}:',
      flush=True,
  )

  if run_slurm_job_list_command(args):
    xpk_exit(1)
  xpk_exit(0)


def run_slurm_job_list_command(args) -> None:
  cmd = (
      f'kubectl-kjob list slurm  --profile {APP_PROFILE_TEMPLATE_DEFAULT_NAME}'
  )

  return_code = run_command_with_updates(cmd, 'list slurm jobs', args)
  if return_code != 0:
    xpk_print(f'Listing jobs returned ERROR {return_code}')
  xpk_exit(return_code)


def job_cancel(args) -> None:
  """Function around job cancel.

  Args:
    args: user provided arguments for running the command.

  Returns:
    None
  """
  xpk_print(f'Starting job cancel for job: {args.name}', flush=True)
  add_zone_and_project(args)

  return_code = run_slurm_job_delete_command(args)
  xpk_exit(return_code)


def run_slurm_job_delete_command(args) -> int:
  list_of_jobs = ' '.join(args.name)
  cmd = f'kubectl-kjob delete slurm {list_of_jobs}'

  return_code = run_command_with_updates(cmd, 'delete slurm job', args)
  if return_code != 0:
    xpk_print(f'Delete job request returned ERROR {return_code}')
  return return_code
