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

from ..utils.console import xpk_print
from ..utils.file import write_tmp_file
from .capacity import H100_DEVICE_TYPE
from .commands import run_command_for_value, run_command_with_updates
from .gcloud_context import zone_to_region
from .system_characteristics import SystemCharacteristics

# cluster_network_yaml: the config when creating the network for a3 cluster
CLUSTER_NETWORK_YAML = """
apiVersion: networking.gke.io/v1
kind: Network
metadata:
  name: vpc1
spec:
  parametersRef:
    group: networking.gke.io
    kind: GKENetworkParamSet
    name: vpc1
  type: Device
---
apiVersion: networking.gke.io/v1
kind: Network
metadata:
  name: vpc2
spec:
  parametersRef:
    group: networking.gke.io
    kind: GKENetworkParamSet
    name: vpc2
  type: Device
---
apiVersion: networking.gke.io/v1
kind: Network
metadata:
  name: vpc3
spec:
  parametersRef:
    group: networking.gke.io
    kind: GKENetworkParamSet
    name: vpc3
  type: Device
---
apiVersion: networking.gke.io/v1
kind: Network
metadata:
  name: vpc4
spec:
  parametersRef:
    group: networking.gke.io
    kind: GKENetworkParamSet
    name: vpc4
  type: Device
---
apiVersion: networking.gke.io/v1
kind: GKENetworkParamSet
metadata:
  name: vpc1
spec:
  vpc: {cluster_name}-net-1
  vpcSubnet: {cluster_name}-sub-1
  deviceMode: NetDevice
---
apiVersion: networking.gke.io/v1
kind: GKENetworkParamSet
metadata:
  name: vpc2
spec:
  vpc: {cluster_name}-net-2
  vpcSubnet: {cluster_name}-sub-2
  deviceMode: NetDevice
---
apiVersion: networking.gke.io/v1
kind: GKENetworkParamSet
metadata:
  name: vpc3
spec:
  vpc: {cluster_name}-net-3
  vpcSubnet: {cluster_name}-sub-3
  deviceMode: NetDevice
---
apiVersion: networking.gke.io/v1
kind: GKENetworkParamSet
metadata:
  name: vpc4
spec:
  vpc: {cluster_name}-net-4
  vpcSubnet: {cluster_name}-sub-4
  deviceMode: NetDevice
"""


def create_cluster_network(args, index) -> int:
  """Create one GKE Cluster network.

  Args:
    args: user provided arguments for running the command.
    index: index number for the network to be created.

  Returns:
    0 if successful and 1 otherwise.
  """
  existing_network_names, return_code = get_all_networks_programmatic(args)
  if return_code > 0:
    xpk_print('Listing all networks failed!')
    return return_code

  network_name = f'{args.cluster}-net-{index}'
  if network_name not in existing_network_names:
    command = (
        f'gcloud compute --project={args.project}'
        f' networks create {network_name}'
        ' --subnet-mode=custom --mtu=8244'
    )
    return_code = run_command_with_updates(
        command, 'Create Cluster Network', args, verbose=False
    )

    if return_code != 0:
      xpk_print(f'Create Cluster Network request returned ERROR {return_code}')
      return 1
  else:
    xpk_print(f'Reusing existing network {network_name}')

  return 0


def create_cluster_subnet(args, index) -> int:
  """Create one GKE Cluster subnet.

  Args:
    args: user provided arguments for running the command.
    index: index number for the subnet to be created.

  Returns:
    0 if successful and 1 otherwise.
  """
  existing_subnet_names, return_code = get_all_subnets_programmatic(args)
  if return_code > 0:
    xpk_print('Listing all subnets failed!')
    return return_code
  subnet_name = f'{args.cluster}-{zone_to_region(args.zone)}-sub-{index}'
  if subnet_name not in existing_subnet_names:
    command = (
        f'gcloud compute --project={args.project}'
        f' networks subnets create {subnet_name}'
        f' --network={args.cluster}-net-{index}'
        f' --region={zone_to_region(args.zone)} --range=192.168.{index}.0/24'
    )
    return_code = run_command_with_updates(
        command, 'Create Cluster Subnet', args, verbose=False
    )

    if return_code != 0:
      xpk_print(f'Create Cluster Subnet request returned ERROR {return_code}')
      return 1
  else:
    xpk_print(f'Reusing existing subnet {subnet_name}')

  return 0


def get_subnetworks_for_a3mega(cluster_name: str) -> list[str]:
  return [f'{cluster_name}-gpunet-{i}-subnet' for i in range(8)]


def get_subnetworks_for_a3ultra(cluster_name: str) -> list[str]:
  return [f'{cluster_name}-sub-1'] + [
      f'{cluster_name}-rdma-sub-{i}' for i in range(8)
  ]


def create_cluster_firewall_rule(args, index) -> int:
  """Create one GKE Cluster firewall rule.

  Args:
    args: user provided arguments for running the command.
    index: index number for the firewall rule to be created.

  Returns:
    0 if successful and 1 otherwise.
  """
  existing_firewall_rules_names, return_code = (
      get_all_firewall_rules_programmatic(args)
  )
  if return_code > 0:
    xpk_print('Listing all firewall rules failed!')
    return return_code
  firewall_rule_name = f'{args.cluster}-internal-{index}'
  if firewall_rule_name not in existing_firewall_rules_names:
    command = (
        f'gcloud compute --project={args.project} firewall-rules create'
        f' {firewall_rule_name} --network={args.cluster}-net-{index} --action=ALLOW'
        ' --rules=tcp:0-65535,udp:0-65535,icmp --source-ranges=192.168.0.0/16'
    )
    return_code = run_command_with_updates(
        command, 'Create Cluster Firewall Rule', args, verbose=False
    )

    if return_code != 0:
      xpk_print(
          f'Create Cluster Firewall Rule request returned ERROR {return_code}'
      )
      return 1
  else:
    xpk_print(f'Reusing existing firewall rule {firewall_rule_name}')
  return 0


def create_cluster_network_config(args) -> int:
  """Run the Create GKE Cluster Network Config request.

  Args:
    args: user provided arguments for running the command.

  Returns:
    0 if successful and 1 otherwise.
  """
  yml_string = CLUSTER_NETWORK_YAML.format(cluster_name=args.cluster)
  tmp = write_tmp_file(yml_string)
  command = f'kubectl apply -f {str(tmp.file.name)}'

  return_code = run_command_with_updates(
      command, 'GKE Cluster Create Network Config', args
  )
  if return_code != 0:
    xpk_print(
        f'GKE Cluster Create ConfigMap request returned ERROR {return_code}'
    )
    return 1

  return 0


def set_up_cluster_network_for_gpu(args, system: SystemCharacteristics) -> int:
  """Set up GKE Cluster networks, subnets and firewall rules for A3/A3+.
  Note: there are 4 NICs for GPU-GPU bw and 1 NIC for host in an A3 node,
  and there are 8 NICs for GPU-GPU bw and 1 NIC for host in an A3+ node.

  Args:
    args: user provided arguments for running the command.
    system: system characteristics.

  Returns:
    0 if successful and 1 otherwise.
  """
  num_networks = 5 if system.device_type == H100_DEVICE_TYPE else 9
  for i in range(1, num_networks):
    return_code = create_cluster_network(args, i)
    if return_code != 0:
      return 1
    return_code = create_cluster_subnet(args, i)
    if return_code != 0:
      return 1
    return_code = create_cluster_firewall_rule(args, i)
    if return_code != 0:
      return 1
  return 0


def delete_cluster_subnets(args) -> int:
  """Delete GKE Cluster subnets.

  Args:
    args: user provided arguments for running the command.

  Returns:
    0 if successful and 1 otherwise.
  """
  existing_subnet_names, return_code = get_all_subnets_programmatic(args)
  if return_code > 0:
    xpk_print('Listing all subnets failed!')
    return return_code

  for subnet_name in existing_subnet_names:
    command = (
        f'gcloud compute networks subnets delete {subnet_name}'
        f' --region={zone_to_region(args.zone)} --project={args.project} --quiet'
    )

    return_code = run_command_with_updates(
        command, 'Delete Cluster Subnet', args, verbose=False
    )

    if return_code != 0:
      xpk_print(f'Delete Cluster Subnet request returned ERROR {return_code}')
      return 1
    else:
      xpk_print(f'Deleted existing subnet {subnet_name}')

  return 0


def get_all_networks_programmatic(args) -> tuple[list[str], int]:
  """Gets all the networks associated with project .

  Args:
    args: user provided arguments for running the command.

  Returns:
    List of networks and 0 if successful and 1 otherwise.
  """
  command = 'gcloud compute networks list --format="csv[no-heading](name)"'
  return_code, raw_network_output = run_command_for_value(
      command, 'Get All Networks', args
  )
  if return_code != 0:
    xpk_print(f'Get All Networks returned ERROR {return_code}')
    return [], 1

  return raw_network_output.splitlines(), 0


def get_all_subnets_programmatic(args) -> tuple[list[str], int]:
  """Gets all the subnets associated with the project.

  Args:
    args: user provided arguments for running the command.

  Returns:
    List of subnets and 0 if successful and 1 otherwise.
  """
  subnet_name_filter = f'{args.cluster}-{zone_to_region(args.zone)}-sub-*'

  command = (
      'gcloud compute networks subnets list'
      f' --filter=name~"{subnet_name_filter}" --project={args.project}'
  )
  return_code, raw_subnets_output = run_command_for_value(
      command, 'Get All Subnets', args
  )
  if return_code != 0:
    xpk_print(f'Get All Subnets returned ERROR {return_code}')
    return [], 1

  all_outputs = raw_subnets_output.splitlines()
  all_networks = [
      all_outputs[i].split(' ')[0] for i in range(1, len(all_outputs))
  ]
  return all_networks, 0


def get_all_firewall_rules_programmatic(args) -> tuple[list[str], int]:
  """Gets all the firewall rules associated with the project.

  Args:
    args: user provided arguments for running the command.

  Returns:
    List of firewall rules and 0 if successful and 1 otherwise.
  """
  command = (
      'gcloud compute firewall-rules list --format="csv[no-heading](name)"'
  )
  return_code, raw_subnets_output = run_command_for_value(
      command, 'Get All Firewall Rules', args
  )
  if return_code != 0:
    xpk_print(f'Get All Firewall Rules returned ERROR {return_code}')
    return [], 1

  return raw_subnets_output.splitlines(), 0
