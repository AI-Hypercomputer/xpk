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

from ..core.commands import run_command_with_updates_retry
from ..core.capacity import H100_MEGA_DEVICE_TYPE, CapacityType
from ..core.gcloud_context import get_cluster_location
from ..utils.console import xpk_print, xpk_exit
from ..utils.execution_context import is_dry_run
from ..core.system_characteristics import (
    SystemCharacteristics,
)


def set_cluster_command(args) -> int:
  """Run cluster configuration command to set the kubectl config.

  Args:
    args: user provided arguments for running the command.

  Returns:
    0 if successful and 1 otherwise.
  """
  command = (
      'gcloud container clusters get-credentials'
      f' {args.cluster} --location={get_cluster_location(args.project, args.cluster, args.zone)} --dns-endpoint'
      f' --project={args.project} && kubectl config view && kubectl config'
      ' set-context --current --namespace=default'
  )
  task = f'get-credentials to cluster {args.cluster}'
  return_code = run_command_with_updates_retry(command, task, verbose=False)
  if return_code != 0:
    xpk_print(f'{task} returned ERROR {return_code}')
  return return_code


def is_TAS_possible(
    system_characteristics: SystemCharacteristics | None,
    capacity_type: CapacityType | None,
) -> bool:
  """Check cluster's machine_type and capacity type to determine if Kueue TAS is possible"""

  if is_dry_run():
    return True

  if system_characteristics is None:
    xpk_print('system_characteristics data was not found in configmaps.')
    xpk_exit(1)

  if capacity_type is None:
    xpk_print('capacity_type data was not found in configmaps.')
    xpk_exit(1)

  return (
      system_characteristics.device_type != H100_MEGA_DEVICE_TYPE
      or capacity_type == CapacityType.RESERVATION
  )


def validate_sub_slicing_system(system: SystemCharacteristics):
  if not system.supports_sub_slicing:
    xpk_print(f'Error: {system.device_type} does not support Sub-slicing.')
    xpk_exit(1)


def validate_super_slicing_system(system: SystemCharacteristics):
  if not system.supports_super_slicing:
    xpk_print(f'Error: {system.device_type} does not support Super-slicing.')
    xpk_exit(1)
