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

from ..utils import  xpk_exit, xpk_print
from ..core.kueue import verify_kueuectl_installation, install_kueuectl
from ..core.commands import (
    run_command_for_value,
)

def prepare_kueuectl(args) -> int:
  """Verify if kueuectl is installed. If not install kueuectl.
  Args:
    args: user provided arguments.
  Returns:
    0 if succesful and 1 otherwise.
  """
  xpk_print('Veryfing kueuectl installation')
  args.dry_run = False
  verify_kueuectl_installed_code = verify_kueuectl_installation(args)
  if verify_kueuectl_installed_code == 0:
    xpk_print('kueuectl installed')
    return 0

  if verify_kueuectl_installed_code != 0:
    xpk_print('Installing kueuectl')
    kueuectl_installation_code = install_kueuectl(args)
    if kueuectl_installation_code != 0:
      return kueuectl_installation_code

def info_localqueues(args) -> None:
  """Function around list localqueue.

  Args:
    args: user provided arguments for running the command.
  Returns:
    0 if successful and 1 otherwise.
  """
  installation_code = prepare_kueuectl(args)
  if installation_code != 0:
    xpk_exit(installation_code)

  code = run_kueuectl_list_localqueue(args)
  if code != 0:
    xpk_exit(code)
  return


def info_clustersqueues(args) -> None:
  """Function around list clusterqueue.

  Args:
    args: user provided arguments for running the command.
  Returns:
    0 if successful and 1 otherwise.
  """

  installation_code = prepare_kueuectl(args)
  if installation_code != 0:
    xpk_exit(installation_code)

  code = run_kueuectl_list_clusterqueue(args)

  if code != 0:
    xpk_exit(code)
  return

def run_kueuectl_list_localqueue(args) -> int:
  """Run the kueuectl list localqueue command.

  Args:
    args: user provided arguments for running the command.

  Returns:
    0 if successful and 1 otherwise.
  """
  command = (
      'kubectl kueue list localqueue'
  )
  if args.cluster is not None:
    command += f' --cluster={args.cluster}'
  args.dry_run = False
  return_code, val = run_command_for_value(command, 'List clusterqueues', args)
  if return_code != 0:
    xpk_print(f'Cluster info request returned ERROR {return_code}')
    return 1
  xpk_print(val)
  return 0

def run_kueuectl_list_clusterqueue(args) -> int:
  """Run the kueuectl list clusterqueue command.

  Args:
    args: user provided arguments for running the command.

  Returns:
    0 if successful and 1 otherwise.
  """
  command = (
      'kubectl kueue list clusterqueue'
  )

  if args.cluster is not None:
    command += f' --cluster={args.cluster}'
  args.dry_run = False
  return_code, val = run_command_for_value(command, 'List clusterqueues', args)
  if return_code != 0:
    xpk_print(f'Cluster info request returned ERROR {return_code}')
    return 1
  xpk_print(val)
  return 0
