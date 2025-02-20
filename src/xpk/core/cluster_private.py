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
from ..utils.network import (
    add_current_machine_to_networks,
    is_current_machine_in_any_network,
)
from ..utils.objects import is_text_true
from .commands import run_command_for_value, run_command_with_updates
from .gcloud_context import zone_to_region


def authorize_private_cluster_access_if_necessary(args) -> int:
  """Updates a GKE cluster to add authorize networks to access a private cluster's control plane, if not added already.

  Args:
    args: user provided arguments for running the command.

  Returns:
    0 if successful and error code otherwise.
  """
  if not is_cluster_private(args):
    if not args.private and args.authorized_networks is None:
      xpk_print('Cluster is public and no need to authorize networks.')
      return 0
    else:
      xpk_print(
          'Cannot convert an existing public cluster to private. The arguments'
          ' --private and --authorized-networks are not acceptable for public'
          ' clusters.'
      )
      return 1

  new_authorized_networks_needed, authorized_networks = (
      check_if_new_authorized_networks_needed(args)
  )

  (
      add_current_machine_to_networks_return_code,
      is_current_machine_in_network,
      authorized_networks,
  ) = add_current_machine_to_networks_if_needed(authorized_networks)
  if add_current_machine_to_networks_return_code != 0:
    return add_current_machine_to_networks_return_code

  if new_authorized_networks_needed or not is_current_machine_in_network:
    return update_cluster_new_authorized_networks(args, authorized_networks)

  xpk_print("Current machine's IP adrress is already authorized.")
  return 0


def update_cluster_new_authorized_networks(args, authorized_networks) -> int:
  cluster_authorized_networks_update_code = update_cluster_authorized_networks(
      args, authorized_networks
  )
  if cluster_authorized_networks_update_code != 0:
    xpk_print('Updating cluster authorized networks failed!')
    return cluster_authorized_networks_update_code

  xpk_print("Cluster's master authorized networks updated successfully.")
  return 0


def add_current_machine_to_networks_if_needed(
    authorized_networks,
) -> tuple[int, bool, list]:
  is_current_machine_in_network_return_code, is_current_machine_in_network = (
      is_current_machine_in_any_network(authorized_networks)
  )
  if is_current_machine_in_network_return_code != 0:
    xpk_print("Error on checking current machine's IP adrress.")
    return is_current_machine_in_network_return_code, False, authorized_networks

  if not is_current_machine_in_network:
    add_current_machine_to_networks_return_code, authorized_networks = (
        add_current_machine_to_networks(authorized_networks)
    )
    if add_current_machine_to_networks_return_code != 0:
      xpk_print(
          "Adding current machine's IP address to the authorized networks"
          ' failed!'
      )
      return add_current_machine_to_networks_return_code, authorized_networks

  return 0, is_current_machine_in_network, authorized_networks


def check_if_new_authorized_networks_needed(args) -> tuple[bool, list]:
  new_authorized_networks_needed = args.authorized_networks is not None

  authorized_networks = (
      args.authorized_networks
      if new_authorized_networks_needed
      else get_cluster_authorized_networks(args)
  )

  return new_authorized_networks_needed, authorized_networks


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
      'Check if Private Nodes is enabled in cluster.',
      args,
  )

  if return_code != 0:
    xpk_print('Checking if Private Nodes is enabled failed!')
    xpk_exit(return_code)

  if is_text_true(private_nodes_enabled):
    xpk_print('Private Nodes is enabled on the cluster.')
    return True

  xpk_print('Private Nodes is not enabled on the cluster.')
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
