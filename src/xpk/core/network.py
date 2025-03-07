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
from .capacity import DeviceType
from .commands import run_command_for_value, run_command_with_updates
from .gcloud_context import GCloudContextManager
from .system_characteristics import SystemCharacteristics


class ClusterNetworkManager:
  """Manages GKE Cluster network operations, including creation, deletion, and configuration."""

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

  def __init__(self, args):
    self.args = args

  def create_network(self, index) -> int:
    """Create one GKE Cluster network.

    Args:
      index: index number for the network to be created.

    Returns:
      0 if successful and 1 otherwise.
    """
    existing_network_names, return_code = self.get_all_networks()
    if return_code > 0:
      xpk_print('Listing all networks failed!')
      return return_code

    network_name = f'{self.args.cluster}-net-{index}'
    if network_name not in existing_network_names:
      command = (
          f'gcloud compute --project={self.args.project}'
          f' networks create {network_name}'
          ' --subnet-mode=custom --mtu=8244'
      )
      return_code = run_command_with_updates(
          command, 'Create Cluster Network', self.args, verbose=False
      )

      if return_code != 0:
        xpk_print(
            f'Create Cluster Network request returned ERROR {return_code}'
        )
        return 1

    xpk_print(f'Reusing existing network {network_name}')

    return 0

  def create_subnet(self, index) -> int:
    """Create one GKE Cluster subnet.

    Args:
      index: index number for the subnet to be created.

    Returns:
      0 if successful and 1 otherwise.
    """
    existing_subnet_names, return_code = self.get_all_subnets()
    if return_code > 0:
      xpk_print('Listing all subnets failed!')
      return return_code

    subnet_name = f'{self.args.cluster}-{GCloudContextManager.zone_to_region(self.args.zone)}-sub-{index}'
    if subnet_name not in existing_subnet_names:
      command = (
          f'gcloud compute --project={self.args.project}'
          f' networks subnets create {subnet_name}'
          f' --network={self.args.cluster}-net-{index}'
          f' --region={GCloudContextManager.zone_to_region(self.args.zone)} --range=192.168.{index}.0/24'
      )
      return_code = run_command_with_updates(
          command, 'Create Cluster Subnet', self.args, verbose=False
      )

      if return_code != 0:
        xpk_print(f'Create Cluster Subnet request returned ERROR {return_code}')
        return 1

    xpk_print(f'Reusing existing subnet {subnet_name}')

    return 0

  def create_firewall_rule(self, index) -> int:
    """Create one GKE Cluster firewall rule.

    Args:
      index: index number for the firewall rule to be created.

    Returns:
      0 if successful and 1 otherwise.
    """
    existing_firewall_rules_names, return_code = self.get_all_firewall_rules()
    if return_code > 0:
      xpk_print('Listing all firewall rules failed!')
      return return_code

    firewall_rule_name = f'{self.args.cluster}-internal-{index}'
    if firewall_rule_name not in existing_firewall_rules_names:
      command = (
          f'gcloud compute --project={self.args.project} firewall-rules create'
          f' {firewall_rule_name} --network={self.args.cluster}-net-{index} --action=ALLOW'
          ' --rules=tcp:0-65535,udp:0-65535,icmp'
          ' --source-ranges=192.168.0.0/16'
      )
      return_code = run_command_with_updates(
          command, 'Create Cluster Firewall Rule', self.args, verbose=False
      )

      if return_code != 0:
        xpk_print(
            f'Create Cluster Firewall Rule request returned ERROR {return_code}'
        )
        return 1

    xpk_print(f'Reusing existing firewall rule {firewall_rule_name}')

    return 0

  def create_network_config(self) -> int:
    """Run the Create GKE Cluster Network Config request.

    Returns:
      0 if successful and 1 otherwise.
    """
    yml_string = self.CLUSTER_NETWORK_YAML.format(
        cluster_name=self.args.cluster
    )
    tmp = write_tmp_file(yml_string)
    command = f'kubectl apply -f {str(tmp.file.name)}'

    return_code = run_command_with_updates(
        command, 'GKE Cluster Create Network Config', self.args
    )
    if return_code != 0:
      xpk_print(
          f'GKE Cluster Create ConfigMap request returned ERROR {return_code}'
      )
      return 1

    return 0

  def set_up_network_for_gpu(self, system: SystemCharacteristics) -> int:
    """Set up GKE Cluster networks, subnets and firewall rules for A3/A3+.
    Note: there are 4 NICs for GPU-GPU bw and 1 NIC for host in an A3 node,
    and there are 8 NICs for GPU-GPU bw and 1 NIC for host in an A3+ node.

    Args:
      args: user provided arguments for running the command.
      system: system characteristics.

    Returns:
      0 if successful and 1 otherwise.
    """
    num_networks = 5 if system.device_type == DeviceType.H100.value else 9
    for i in range(1, num_networks):
      return_code = self.create_network(i)
      if return_code != 0:
        return 1
      return_code = self.create_subnet(i)
      if return_code != 0:
        return 1
      return_code = self.create_firewall_rule(i)
      if return_code != 0:
        return 1
    return 0

  def delete_subnets(self) -> int:
    """Delete GKE Cluster subnets.

    Args:
      args: user provided arguments for running the command.

    Returns:
      0 if successful and 1 otherwise.
    """
    existing_subnet_names, return_code = self.get_all_subnets()
    if return_code > 0:
      xpk_print('Listing all subnets failed!')
      return return_code

    for subnet_name in existing_subnet_names:
      command = (
          f'gcloud compute networks subnets delete {subnet_name}'
          f' --region={GCloudContextManager.zone_to_region(self.args.zone)} --project={self.args.project} --quiet'
      )

      return_code = run_command_with_updates(
          command, 'Delete Cluster Subnet', self.args, verbose=False
      )
      if return_code != 0:
        xpk_print(f'Delete Cluster Subnet request returned ERROR {return_code}')
        return 1

      xpk_print(f'Deleted existing subnet {subnet_name}')

    return 0

  def get_all_networks(self) -> tuple[list[str], int]:
    """Gets all the networks associated with project .

    Returns:
      List of networks and 0 if successful and 1 otherwise.
    """
    command = 'gcloud compute networks list --format="csv[no-heading](name)"'
    return_code, raw_network_output = run_command_for_value(
        command, 'Get All Networks', self.args
    )
    if return_code != 0:
      xpk_print(f'Get All Networks returned ERROR {return_code}')
      return [], 1

    return raw_network_output.splitlines(), 0

  def get_all_subnets(self) -> tuple[list[str], int]:
    """Gets all the subnets associated with the project.

    Returns:
      List of subnets and 0 if successful and 1 otherwise.
    """
    command = (
        'gcloud compute networks subnets list'
        f' --filter=name~"{self.args.cluster}-{GCloudContextManager.zone_to_region(self.args.zone)}-sub-*"'
        f' --project={self.args.project}'
    )
    return_code, raw_subnets_output = run_command_for_value(
        command, 'Get All Subnets', self.args
    )
    if return_code != 0:
      xpk_print(f'Get All Subnets returned ERROR {return_code}')
      return [], 1

    all_outputs = raw_subnets_output.splitlines()
    all_networks = [
        all_outputs[i].split(' ')[0] for i in range(1, len(all_outputs))
    ]
    return all_networks, 0

  def get_all_firewall_rules(self) -> tuple[list[str], int]:
    """Gets all the firewall rules associated with the project.

    Returns:
      List of firewall rules and 0 if successful and 1 otherwise.
    """
    command = (
        'gcloud compute firewall-rules list --format="csv[no-heading](name)"'
    )
    return_code, raw_subnets_output = run_command_for_value(
        command, 'Get All Firewall Rules', self.args
    )
    if return_code != 0:
      xpk_print(f'Get All Firewall Rules returned ERROR {return_code}')
      return [], 1

    return raw_subnets_output.splitlines(), 0
