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

import urllib
from ..core.commands import run_command_for_value, run_command_with_updates, run_commands
from ..core.gcloud_context import get_cluster_location
from ..core.nodepool import get_all_nodepools_programmatic
from ..utils.console import xpk_exit, xpk_print
from ..utils.execution_context import is_dry_run
from .system_characteristics import AcceleratorType


def ensure_pathways_workload_prerequisites(args, system) -> bool:
  """Check all Pathways workload prerequisites and set necessary args.

  Args:
    args: user provided arguments for running the command.
    system: system characteristics.

  Returns:
    True once conditions satisfy and variables are set. Exits otherwise.
  """
  # Ensure command is provided if not using Pathways in headless mode
  if args.command is None and not args.headless:
    xpk_print(
        'Please provide a command using "--command" for the docker container to'
        ' execute. Command is not required if you wish to run Pathways'
        ' workloads in headless mode (`xpk workload create-pathways'
        ' --headless`).'
    )
    xpk_exit(1)

  # Ensure the cluster and CPU nodepools were created with create-pathways
  all_node_pools = get_all_nodepools_programmatic(args)
  desired_pw_cpu_node_pools = {'cpu-np'}
  if (
      not desired_pw_cpu_node_pools.issubset(set(all_node_pools[0]))
      and not is_dry_run()
  ):
    xpk_print(
        'Cluster needs to be created with `xpk create-pathways` to run'
        ' Pathways workloads.'
    )
    xpk_exit(1)

  # Ensure device type is TPUs - currently Pathways supports TPUs only.
  if system.accelerator_type != AcceleratorType.TPU:
    xpk_print('Currently, Pathways workloads can only be run on TPUs.')
    xpk_exit(1)

  # Note: The legacy Go controller supported 'colocate_head_with_workers' to run the proxy/RM on TPU nodes.
  # This feature is deprecated in the new JobSet migration. The pathways-head will run on the CPU node pool.

  # Set proxy address to be consumed in helper methods and displayed to user.
  args.pathways_proxy_address = get_proxy_address(args)

  return True


def check_if_pathways_job_is_installed(args) -> bool:
  """Check if PathwaysJob is installed on the cluster.
  Args:
    args: user provided arguments for running the command.
  Returns:
    0 if successful and 1 otherwise.
  """
  command = (
      'kubectl get pods -n pathways-job-system --no-headers -o'
      ' custom-columns=NAME:.metadata.name'
  )
  task = f'Check if PathwaysJob is installed on {args.cluster}'
  return_code, return_msg = run_command_for_value(command, task)
  # return_msg contains the name of the controller pod, if found.
  xpk_print('check_if_pathways_job_is_installed', return_code, return_msg)

  if return_code != 0:
    xpk_print(f'{task} returned with ERROR {return_code}.\n')
    return False
  if not return_msg:
    xpk_print(
        'You are using a new version of XPK, which uses PathwaysJob'
        ' for Pathways workloads. Please update the cluster using'
        ' `cluster create-pathways` to enjoy the upgrade!'
    )
    return False
  return True


def get_pathways_unified_query_link(args) -> str:
  """Get the unified query link for the pathways workload."""
  log_filter = (
      'resource.type="k8s_container"\n'
      f'resource.labels.project_id="{args.project}"\n'
      f'resource.labels.location="{get_cluster_location(args.project, args.cluster, args.zone)}"\n'
      f'resource.labels.cluster_name="{args.cluster}"\n'
      f'resource.labels.pod_name:"{args.workload}-"\n'
      'severity>=DEFAULT'
  )
  encoded_filter = urllib.parse.quote(log_filter, safe='')

  return f'https://console.cloud.google.com/logs/query;query={encoded_filter}'


def get_proxy_address(args) -> str:
  """Generates the Pathways proxy address.
  Args:
    args: user provided arguments for running the command.

  Returns:
    str: Fully qualified proxy address.
  """
  proxy_address = (
      f'grpc://{args.workload}-pathways-head-0-0.{args.workload}:29000'
  )
  return proxy_address


def try_to_delete_pathwaysjob_first(args, workloads) -> bool:
  """Function to delete PathwaysJob workload. This is needed as PathwaysJob
  owns the JobSet it creates.

  Args:
    args: user provided arguments for running the command.
    workloads: list of workloads that match the delete filter.

  Returns:
    True if successful and False otherwise.
  """
  commands = []
  task_names = []
  for workload in workloads:
    args.workload = workload
    command = f'kubectl delete pathwaysjob {workload} -n default'
    task_name = f'PathwaysWorkloadDelete-{workload}'
    commands.append(command)
    task_names.append(task_name)

  # Not batching deletion for single workload
  if len(workloads) == 1:
    return_code = run_command_with_updates(commands[0], 'Delete Workload')
  else:
    maybe_failure = run_commands(
        commands, 'Delete Workload', task_names, batch=100
    )
    return_code = 0 if not maybe_failure else maybe_failure[0].return_code

  if return_code != 0:
    xpk_print(f'Delete Workload request returned ERROR {return_code}')
    return False
  return True


def get_pathways_machine_types(
    project: str, zone: str
) -> tuple[int, list[str]]:
  # Identify machine types with sufficient allocatable capacity to
  # schedule the Pathways pod. This filter ensures the selected node
  # is large enough to handle the control plane workload plus GKE
  # system overhead.
  min_memory_mb = 233 * 1024
  command = (
      'gcloud compute machine-types list --filter "guestCpus >= 49 AND memoryMb'
      f' >= {min_memory_mb} AND zone = \'{zone}\'" --format="value(name)"'
      f' --project={project}'
  )
  return_code, result = run_command_for_value(
      command=command,
      task='Retrieve available pathways machine types',
      dry_run_return_val='n2-standard-64',
  )
  if return_code != 0:
    return return_code, []
  return 0, result.strip().splitlines()
