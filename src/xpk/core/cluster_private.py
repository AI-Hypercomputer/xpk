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

from .core import zone_to_region
from .commands import run_command_for_value, run_command_with_updates
from ..utils.console import xpk_exit, xpk_print
from ..utils.network import add_current_machine_to_networks, is_current_machine_in_any_network


def authorize_private_cluster_access_if_necessary(args) -> int:
  """Updates a GKE cluster to add authorize networks to access a private cluster's control plane, if not added already.

  Args:
    args: user provided arguments for running the command.

  Returns:
    0 if successful and error code otherwise.
  """
  if not is_cluster_private(args):
    if not args.private and args.authorized_networks is None:
      return 0
    else:
      xpk_print(
          'Cannot convert an existing public cluster to private. The arguments'
          ' --private and --authorized-networks are not acceptable for public'
          ' clusters.'
      )
      return 1

  if args.authorized_networks is not None:
    return_code, authorized_networks = add_current_machine_to_networks(
        args.authorized_networks
    )
    if return_code > 0:
      xpk_print(
          "Adding current machine's IP address to the authorized networks"
          ' failed!'
      )
      return return_code
    update_authorized_networks = True
  else:
    existing_authorized_networks = get_cluster_authorized_networks(args)
    update_authorized_networks = not is_current_machine_in_any_network(
        existing_authorized_networks
    )
    authorized_networks = add_current_machine_to_networks(
        existing_authorized_networks
    )

  if update_authorized_networks:
    cluster_authorized_networks_update_code = (
        update_cluster_authorized_networks(args, authorized_networks)
    )
    if cluster_authorized_networks_update_code > 0:
      xpk_print('Updating cluster authorized networks failed!')
      return cluster_authorized_networks_update_code
  return 0


def is_cluster_private(args) -> bool:
  """Checks if cluster is private.
  Args:
    args: user provided arguments for running the command.

  Returns:
    True if cluster is private and False otherwise.
  """
  command = (
      f'gcloud container clusters describe {args.cluster}'
      f' --project={args.project} --region={zone_to_region(args.zone)}'
      ' --format="value(privateClusterConfig.enablePrivateNodes)"'
  )
  return_code, private_nodes_enabled = run_command_for_value(
      command,
      'Check if Private Nodes is enabled in cluster describe.',
      args,
  )

  if return_code != 0:
    xpk_print('Checking if Private Nodes is enabled failed!')
    xpk_exit(return_code)

  if private_nodes_enabled.lower() == 'true':
    xpk_print('Private Nodes is enabled on the cluster.')
    return True
  return False


def get_cluster_authorized_networks(args) -> list[str]:
  """Retreives the networks list that are authorized to have access to Control Plane.
  Args:
    args: user provided arguments for running the command.

  Returns:
    List of networks CIDRs as strings
  """
  command = (
      f'gcloud container clusters describe {args.cluster}'
      f' --project={args.project} --region={zone_to_region(args.zone)}'
      ' --format="value(masterAuthorizedNetworksConfig.cidrBlocks[].cidrBlock)"'
  )
  return_code, authorized_networks = run_command_for_value(
      command,
      'Fetching the list of authorized network from cluster describe.',
      args,
  )

  if return_code != 0:
    xpk_print('Fetching authorized networks failed!')
    xpk_exit(return_code)

  return (
      authorized_networks.strip().split(';')
      if authorized_networks.strip() != ''
      else []
  )


def update_cluster_authorized_networks(args, authorized_networks) -> int:
  """Run the GKE cluster update command for existing cluster and update master authorized networks list.
  Args:
    args: user provided arguments for running the command.
    authorized_networks: list of networks CIDRs to authorize.
  Returns:
    0 if successful and 1 otherwise.
  """
  command = (
      'gcloud container clusters update'
      f' {args.cluster} --project={args.project}'
      f' --region={zone_to_region(args.zone)}'
      ' --enable-master-authorized-networks'
      f' --master-authorized-networks={",".join(authorized_networks)}'
      ' --quiet'
  )

  return_code = run_command_with_updates(
      command, 'GKE Cluster Update master authorized networks', args
  )

  if return_code != 0:
    xpk_print(f'GKE Cluster Update request returned ERROR {return_code}')
    return 1
  return 0
