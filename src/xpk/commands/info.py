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

from ..utils import xpk_exit, xpk_print
from ..core.kueue import verify_kueuectl_installation
from .cluster import set_cluster_command
from ..core.commands import (
    run_command_for_value,
)
from ..core.core import (
    add_zone_and_project,
)
import json
from tabulate import tabulate

table_fmt = 'plain'


def prepare_kueuectl(args) -> int:
  """Verify if kueuectl is installed.
  Args:
    args: user provided arguments.
  Returns:
    0 if succesful and 1 otherwise.
  """
  xpk_print('Veryfing kueuectl installation')
  
  verify_kueuectl_installed_code = verify_kueuectl_installation(args)
  if verify_kueuectl_installed_code == 0:
    xpk_print('kueuectl installed')
    return 0

  if verify_kueuectl_installed_code != 0:
    xpk_print(
        'kueuectl not installed. Please follow'
        ' https://kueue.sigs.k8s.io/docs/reference/kubectl-kueue/installation/'
        ' to install kueuectl.'
    )
    return verify_kueuectl_installed_code


def info(args) -> None:
  """Provide info about localqueues, clusterqueues and their resources.

  Args:
    args: user provided arguments for running the command.
  Returns:
    0 if successful and 1 otherwise.
  """
  add_zone_and_project(args)

  shared_flags_error = apply_shared_flags(args)
  if shared_flags_error != 0:
    xpk_exit(shared_flags_error)

  set_cluster_command_code = set_cluster_command(args)
  if set_cluster_command_code != 0:
    xpk_exit(set_cluster_command_code)

  installation_code = prepare_kueuectl(args)
  if installation_code != 0:
    xpk_exit(installation_code)

  lq_code, lqs = run_kueuectl_list_localqueue(args)
  if lq_code != 0:
    xpk_exit(lq_code)

  cq_code, cqs = run_kueuectl_list_clusterqueue(args)
  if cq_code != 0:
    xpk_exit(cq_code)

  aggregate_results(cqs, lqs)
  return


def apply_shared_flags(args) -> tuple[int, str]:
  """Apply shared flags. It checks --project and --zone
    flags and executes proper gcloud commands if present.

  Args:
    args: user provided args.

  Returns:
    0 if successful and 1 otherwise.
  """
  if args.project is not None:
    project_cmd = f'gcloud config set project {args.project}'
    return_code, _ = run_command_for_value(project_cmd, 'Set gcp project', args)
    if return_code != 0:
      xpk_exit(return_code)

  if args.zone is not None:
    zone_cmd = f'gcloud config set compute/zone {args.zone}'
    return_code, _ = run_command_for_value(zone_cmd, 'set gcloud zone', args)
    if return_code != 0:
      xpk_exit(return_code)

  return 0


def aggregate_results(cqs, lqs) -> None:
  """Aggregate listed clusterqueues and localqueues with resource usage and print them as table.

  Args:
    lqs: list of localqueues.
    cqs: list of clusterqueues.

  """
  cq_list = json.loads(cqs)['items']
  lq_list = json.loads(lqs)['items']

  cq_usages = parse_queue_lists(cq_list, usage_key='flavorsUsage')
  lq_usages = parse_queue_lists(lq_list)

  xpk_print(
      '\n', tabulate(cq_usages + lq_usages, headers='keys', tablefmt=table_fmt)
  )


def parse_queue_lists(
    qs, usage_key='flavorUsage', reservation_key='flavorsReservation'
) -> list[dict]:
  qs_usage_list = []
  for q in qs:
    queue_name = q['metadata']['name']
    q_pending_workloads = q['status']['pendingWorkloads']
    q_admitted_workloads = q['status']['admittedWorkloads']
    q_flavors_usage = {
        'QUEUE': queue_name,
        'ADMITTED WORKLOADS': q_admitted_workloads,
        'PENDING_WORKLOADS': q_pending_workloads,
    }
    q_flavors_usage.update(
        get_flavors_usage(q, usage_field=usage_key, res_field=reservation_key)
    )
    qs_usage_list.append(q_flavors_usage)
  return qs_usage_list


def get_flavors_usage(q_entry, usage_field, res_field) -> list[dict]:
  """Parse q_entry to retrieve list of each resource usage in flavour.

  Args:
    q_entry - single entry into either LocalQueue or ClusterQueue structured as json
    statusField - either "flavorsReservation" or "flavorsUsage"
  Returns:
    list of dicts where each list entry contains two keys:
      - resource - resource name in format flavorName:resourceName
      - usage - usage in format total_usage/total_reservation
  """
  status = q_entry['status']
  flavors_res = status[res_field]
  flavors_usage = status[usage_field]

  flavors_usage = {
      flavor['name']: flavor['resources'] for flavor in flavors_usage
  }
  flavors_res = {flavor['name']: flavor['resources'] for flavor in flavors_res}
  usage_fraction = {}

  for flavor_name, flavor_resources_usage_list in flavors_usage.items():
    flavor_resources_reservation_list = flavors_res[flavor_name]
    flavor_resource_reservation = {
        resource['name']: resource['total']
        for resource in flavor_resources_usage_list
    }
    flavor_resource_usages = {
        resource['name']: resource['total']
        for resource in flavor_resources_reservation_list
    }

    for resource_name in flavor_resource_reservation.keys():
      key = f'{flavor_name}:{resource_name}'
      usage_fmt = f'{flavor_resource_usages[resource_name]}/{flavor_resource_reservation[resource_name]}'
      usage_fraction[key] = usage_fmt
  return usage_fraction


def run_kueuectl_list_localqueue(args) -> tuple[int, str]:
  """Run the kueuectl list localqueue command.

  Args:
    args: user provided arguments for running the command.

  Returns:
    0 if successful and 1 otherwise.
  """
  command = 'kubectl kueue list localqueue -o json'
  return_code, val = run_command_for_value(command, 'list localqueue', args)

  if return_code != 0:
    xpk_print(f'Cluster info request returned ERROR {return_code}')
    return 1, ''
  return 0, val


def run_kueuectl_list_clusterqueue(args) -> int:
  """Run the kueuectl list clusterqueue command.

  Args:
    args: user provided arguments for running the command.

  Returns:
    0 if successful and 1 otherwise.
  """
  command = 'kubectl kueue list clusterqueue -o json'
  return_code, val = run_command_for_value(command, 'list clusterqueue', args)

  if return_code != 0:
    xpk_print(f'Cluster info request returned ERROR {return_code}')
    return 1, ''
  return 0, val
