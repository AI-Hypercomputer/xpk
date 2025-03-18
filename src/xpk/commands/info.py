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

import json
from argparse import Namespace

from tabulate import tabulate

from ..core.commands import run_command_for_value
from ..core.gcloud_context import add_zone_and_project
from ..core.kueue import verify_kueuectl
from ..utils.console import xpk_exit, xpk_print
from .common import set_cluster_command

table_fmt = 'plain'


def info(args: Namespace) -> None:
  """Provide info about localqueues, clusterqueues and their resources.

  Args:
    args: user provided arguments for running the command.
  Returns:
    None
  """
  add_zone_and_project(args)
  set_cluster_command_code = set_cluster_command(args)
  if set_cluster_command_code != 0:
    xpk_exit(set_cluster_command_code)

  verify_kueuectl(args)
  lq, cq = bool(args.localqueue), bool(args.clusterqueue)
  if not lq and not cq:
    lq, cq = True, True

  lqs, cqs = None, None
  if lq:
    lqs = run_kueuectl_list_localqueue(args)

  cqs = run_kueuectl_list_clusterqueue(args)
  quotas = get_nominal_quotas(cqs)

  if lq:
    print_formatted_lqs(lqs, quotas)

  if cq:
    print_formatted_cqs(cqs, quotas)


def get_nominal_quotas(cqs: list[dict]) -> dict[str, dict[str, str]]:
  """Get quotas from clusterqueues.
  This function retrieves how much of resource in each flavor is assigned to cluster queue.
  It parses flavors of passed cluster queues.
  Args:
    - cqs - list of cluster queues.
  Returns:
    - dictionary of cluster queues resources quotas in format:
    {cq_name:{"flavorName:resourceName":quota}}
  """
  try:
    cq_list = json.loads(cqs)['items']
  except ValueError:
    xpk_print('Incorrect respone from list clusterqueue')
    xpk_print(cqs)
    xpk_exit(1)

  quotas = {}
  for cq in cq_list:
    spec = cq['spec']
    cq_name = cq['metadata']['name']
    quotas[cq_name] = {}
    for rg in spec['resourceGroups']:
      for flavor in rg['flavors']:
        name = flavor['name']
        for resource in flavor['resources']:
          key = f'{name}:{resource["name"]}'
          quotas[cq_name][key] = resource['nominalQuota']
  return quotas


def print_formatted_cqs(cqs: list[dict], nominalQuotas) -> None:
  try:
    cq_list = json.loads(cqs)['items']
  except ValueError:
    xpk_print('Incorrect respone from list clusterqueue')
    xpk_print(cqs)
    xpk_exit(1)

  cq_usages = parse_queue_lists(cq_list, nominalQuotas)

  xpk_print(
      'Cluster Queues usage \n',
      tabulate(cq_usages, headers='keys', tablefmt=table_fmt),
  )


def print_formatted_lqs(lqs: list[dict], nominalQuotas) -> None:
  try:
    lq_list = json.loads(lqs)['items']
  except ValueError:
    xpk_print('Incorrect respone from list localqueue')
    xpk_print(lqs)
    xpk_exit(1)

  lq_usages = parse_queue_lists(lq_list, nominalQuotas)
  xpk_print(
      'Local Queues usage \n',
      tabulate(lq_usages, headers='keys', tablefmt=table_fmt),
  )


def parse_queue_lists(
    qs: list[dict],
    flavor_resource_quotas: dict,
    reservation_key: str = 'flavorsReservation',
) -> list[dict]:
  qs_usage_list = []
  for q in qs:
    queue_name = q['metadata']['name']
    q_pending_workloads = q['status']['pendingWorkloads']
    q_admitted_workloads = q['status']['admittedWorkloads']
    q_status = {
        'QUEUE': queue_name,
        'ADMITTED_WORKLOADS': q_admitted_workloads,
        'PENDING_WORKLOADS': q_pending_workloads,
    }
    q_status.update(
        get_flavors_usage(q, reservation_key, flavor_resource_quotas)
    )
    qs_usage_list.append(q_status)
  return qs_usage_list


def get_flavors_resources_reservations(
    cq_name: str, flavors_res: list[dict]
) -> dict[str, dict[str, str]]:
  """Get usage of flavors resources.
  This function parser flavorsReservation section of clusterQueue of LocalQueue.
  Args:
    - cq_name - name of ClusterQueue to which flavors belong.
    - flavors_res - list of reservations made by flavors
  Returns:
    Dict containing usage of each resource in flavor for each flavor in cluster or local queue.
    Dict format: {cq_name: {{flavor:resource}:reservation}}
  """
  reservations = {}
  reservations[cq_name] = {}
  for flavor_name, flavor_resources_reservation_list in flavors_res.items():
    for resource in flavor_resources_reservation_list:
      reservations[cq_name][f'{flavor_name}:{resource["name"]}'] = resource[
          'total'
      ]

  return reservations


def get_flavors_usage(
    q_entry: dict, res_field: str, flavor_resource_quotas: dict
) -> list[dict]:
  """Parse q_entry to retrieve list of each resource usage in flavour.
  Args:
    q_entry - single entry into either LocalQueue or ClusterQueue structured as json
    flavor_resource_quotas - nominalQuota of flavors resource usage for each clusterqueue
  Returns:
    list of dicts where each list entry is in format (key, entry) where:
    - key is flavorName:resourceName
    - entry is flavorResourceReservation/flavorResourceQuota
  """
  status = q_entry['status']
  flavors_res = status[res_field]
  queue_type = q_entry['kind']

  flavors_res = {flavor['name']: flavor['resources'] for flavor in flavors_res}
  usage_fraction = {}
  cq_name = (
      q_entry['metadata']['name']
      if queue_type == 'ClusterQueue'
      else q_entry['spec']['clusterQueue']
  )

  reservations = get_flavors_resources_reservations(cq_name, flavors_res)

  for cq_name, cq_reservations in reservations.items():
    cq_nominal_quotas = flavor_resource_quotas[cq_name]

    for flavor_resource, flavor_resource_quota in cq_nominal_quotas.items():
      flavor_resource_reservation = cq_reservations[flavor_resource]
      usage_fraction[flavor_resource] = (
          f'{flavor_resource_reservation}/{flavor_resource_quota}'
      )
  return usage_fraction


def run_kueuectl_list_localqueue(args: Namespace) -> str:
  """Run the kueuectl list localqueue command.

  Args:
    args: user provided arguments for running the command.

  Returns:
    kueuectl list localqueue formatted as json string.
  """
  command = 'kubectl kueue list localqueue -o json'
  if args.namespace != '':
    command += f' --namespace {args.namespace}'
  return_code, val = run_command_for_value(command, 'list localqueue', args)

  if return_code != 0:
    xpk_print(f'Cluster info request returned ERROR {return_code}')
    xpk_exit(return_code)
  return val


def run_kueuectl_list_clusterqueue(args: Namespace) -> str:
  """Run the kueuectl list clusterqueue command.

  Args:
    args: user provided arguments for running the command.

  Returns:
    kueuectl list clusterqueue formatted as json string
  """
  command = 'kubectl kueue list clusterqueue -o json'

  return_code, val = run_command_for_value(command, 'list clusterqueue', args)

  if return_code != 0:
    xpk_print(f'Cluster info request returned ERROR {return_code}')
    xpk_exit(return_code)
  return val
