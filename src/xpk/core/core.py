"""
Copyright 2023 Google LLC

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

r"""xpk (Accelerated Processing Kit).

Next Steps:
- Cluster describe is broken by Cacheimage since that counts as a workload.
- Cluster describe: count by jobset.
- If any instance goes down, bring down the whole job.
- How to more gracefully handle job failures, distinguishing between software
  and infra?
- Look into --docker-name and --docker-image.
  Shouldn't one string be adequate to express what we want?
- Apply learnings from about private, region, coredns, etc:
- Enable special preheater
- Make Argparse logic this a function?
  - Obvious logic that starts in main instead of here in code but args will
    not be a universal argument.
"""

import datetime
import enum
import os
import random
import re
import string
import subprocess
import sys
from dataclasses import dataclass

from ..utils import get_user_input, write_tmp_file, xpk_exit, xpk_print
from .commands import (
    run_command_for_value,
    run_command_with_updates,
    run_command_with_updates_retry,
    run_commands,
)
from .system_characteristics import (
    AcceleratorType,
    AcceleratorTypeToAcceleratorCharacteristics,
    SystemCharacteristics,
)

################### Internally used constants ##############

default_docker_image = 'python:3.10'
default_script_dir = os.getcwd()
# This is the version for XPK PyPI package
__version__ = '0.5.0'
xpk_current_version = __version__

h100_device_type = 'h100-80gb-8'
h100_mega_device_type = 'h100-mega-80gb-8'


CAPACITY_TYPE_CONFIG_KEY = 'capacity_type'
RESERVATION_CONFIG_KEY = 'reservation_id'
_DEFAULT_POOL_NAME = 'default-pool'
CLUSTER_RESOURCES_CONFIGMAP = 'resources-configmap'
CLUSTER_METADATA_CONFIGMAP = 'metadata-configmap'
VERTEX_TENSORBOARD_FEATURE_FLAG = xpk_current_version >= '0.4.0'
DEFAULT_VERTEX_TENSORBOARD_NAME = 'tb-instance'
AUTOPROVISIONING_CONFIG_VALUE = 'AUTOPROVISION'
AUTOPROVISIONING_CONFIG_MINIMUM_KEY = 'minimum_chips'
AUTOPROVISIONING_CONFIG_MAXIMUM_KEY = 'maximum_chips'


class CapacityType(enum.Enum):
  ON_DEMAND = 'on_demand'
  RESERVATION = 'reservation'
  SPOT = 'spot'
  UNKNOWN = 'unknown'


@dataclass
class AutoprovisioningConfig:
  config_filename: str
  minimum_chips: int
  maximum_chips: int


cluster_configmap_yaml = """kind: ConfigMap
apiVersion: v1
metadata:
  name: {name}
data:
  {data}
"""

# cluster_network_yaml: the config when creating the network for a3 cluster
cluster_network_yaml = """
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


def add_zone_and_project(args):
  """Obtains the zone and project names from gcloud configs if not defined.

  Args:
    args: user provided arguments for running the command.
  """
  if not args.project:
    args.project = get_project()
  if not args.zone:
    args.zone = get_zone()
  xpk_print(f'Working on {args.project=} and {args.zone}')


def parse_env_config(args, tensorboard_config, system: SystemCharacteristics):
  """Parses the environment configurations to the jobset config.

  Args:
    args: user provided arguments for running the command.
    tensorboard_config: configuration of Vertex Tensorboard.
    system: system characteristics.
  """
  env = {'JOBSET_NAME': args.workload}

  env_pat = re.compile(r'(^[a-zA-Z_][a-zA-Z0-9_]*?)(?:=(.*))?$', re.M)
  if args.env_file:
    print('Setting container environment from', args.env_file)
    with open(file=args.env_file, mode='r', encoding='utf-8') as f:
      for match in env_pat.finditer(f.read()):
        variable = match.group(1)
        if match.group(2) is not None:
          env[variable] = match.group(2)
        else:
          assert variable in os.environ, (
              f'Variable {variable} is not set in the current '
              'environment, a value must be specified.'
          )
          env[variable] = os.environ[variable]
  if args.env:
    for var in args.env:
      match = env_pat.match(var)
      assert match and match.group(2) is not None, (
          'Invalid environment variable, format must be '
          f'`--env VARIABLE=value`: {var}'
      )
      variable = match.group(1)
      env[variable] = match.group(2)

  if not args.use_pathways:
    if args.debug_dump_gcs:
      if 'XLA_FLAGS' in env:
        raise ValueError(
            'Conflict: XLA_FLAGS defined in both --debug_dump_gcs '
            'and environment file. Please choose one way to define '
            'XLA_FLAGS.'
        )
      env['XLA_FLAGS'] = '--xla_dump_to=/tmp/xla_dump/'

    if tensorboard_config:
      env['UPLOAD_DATA_TO_TENSORBOARD'] = True
      for key, value in tensorboard_config.items():
        env[key.upper()] = value

  if system.accelerator_type == AcceleratorType['GPU']:
    # For GPUs, it has two more spaces ahead of name and value respectively
    env_format = '''
                  - name: {key}
                    value: "{value}"'''
  else:
    env_format = '''
                - name: {key}
                  value: "{value}"'''

  args.env = ''.join(env_format.format(key=k, value=v) for k, v in env.items())


def get_project():
  """Get GCE project from `gcloud config get project`.

  Returns:
     The project name.
  """
  completed_command = subprocess.run(
      ['gcloud', 'config', 'get', 'project'], check=True, capture_output=True
  )
  project_outputs = completed_command.stdout.decode().strip().split('\n')
  if len(project_outputs) < 1 or project_outputs[-1] == '':
    sys.exit(
        'You must specify the project in the project flag or set it with'
        " 'gcloud config set project <project>'"
    )
  return project_outputs[
      -1
  ]  # The project name lives on the last line of the output


def get_zone():
  """Get GCE zone from `gcloud config get compute/zone`.

  Returns:
     The zone name.
  """
  completed_command = subprocess.run(
      ['gcloud', 'config', 'get', 'compute/zone'],
      check=True,
      capture_output=True,
  )
  zone_outputs = completed_command.stdout.decode().strip().split('\n')
  if len(zone_outputs) < 1 or zone_outputs[-1] == '':
    sys.exit(
        "You must specify the zone in the zone flag or set it with 'gcloud"
        " config set compute/zone <zone>'"
    )
  return zone_outputs[-1]  # The zone name lives on the last line of the output


def zone_to_region(zone) -> str:
  """Helper function converts zone name to region name.

  Args:
    zone: zone name.

  Returns:
     The region name.
  """
  zone_terms = zone.split('-')
  return zone_terms[0] + '-' + zone_terms[1]


def get_total_chips_requested_from_args(
    args, system: SystemCharacteristics
) -> int:
  """Return the total chips requested based on user args.

  Args:
    args: user provided arguments for running the command.
    system: system characteristics.

  Returns:
    num of chips for the current request.
  """
  if system.accelerator_type == AcceleratorType['GPU']:
    num_chips = system.vms_per_slice * system.chips_per_vm * args.num_nodes
  else:
    num_chips = system.vms_per_slice * system.chips_per_vm * args.num_slices

  return num_chips


def update_gke_cluster_with_clouddns(args) -> int:
  """Run the GKE cluster update command for existing clusters and enable CloudDNS.

  Args:
    args: user provided arguments for running the command.

  Returns:
    0 if successful and 1 otherwise.
  """
  command = (
      'gcloud container clusters update'
      f' {args.cluster} --project={args.project}'
      f' --region={zone_to_region(args.zone)}'
      ' --cluster-dns=clouddns'
      ' --cluster-dns-scope=vpc'
      f' --cluster-dns-domain={args.cluster}-domain'
      ' --quiet'
  )
  xpk_print('Updating GKE cluster to use Cloud DNS, may take a while!')
  return_code = run_command_with_updates(
      command, 'GKE Cluster Update to enable Cloud DNS', args
  )
  if return_code != 0:
    xpk_print(f'GKE Cluster Update request returned ERROR {return_code}')
    return 1
  return 0


def update_gke_cluster_with_workload_identity_enabled(args) -> int:
  """Run the GKE cluster update command for existing cluster and enable Workload Identity Federation.
  Args:
    args: user provided arguments for running the command.
  Returns:
    0 if successful and 1 otherwise.
  """
  command = (
      'gcloud container clusters update'
      f' {args.cluster} --project={args.project}'
      f' --region={zone_to_region(args.zone)}'
      f' --workload-pool={args.project}.svc.id.goog'
      ' --quiet'
  )
  xpk_print(
      'Updating GKE cluster to enable Workload Identity Federation, may take a'
      ' while!'
  )
  return_code = run_command_with_updates(
      command, 'GKE Cluster Update to enable Workload Identity Federation', args
  )
  if return_code != 0:
    xpk_print(f'GKE Cluster Update request returned ERROR {return_code}')
    return 1
  return 0


def update_gke_cluster_with_gcsfuse_driver_enabled(args) -> int:
  """Run the GKE cluster update command for existing cluster and enable GCSFuse CSI driver.
  Args:
    args: user provided arguments for running the command.
  Returns:
    0 if successful and 1 otherwise.
  """
  command = (
      'gcloud container clusters update'
      f' {args.cluster} --project={args.project}'
      f' --region={zone_to_region(args.zone)}'
      ' --update-addons GcsFuseCsiDriver=ENABLED'
      ' --quiet'
  )
  xpk_print(
      'Updating GKE cluster to enable GCSFuse CSI driver, may take a while!'
  )
  return_code = run_command_with_updates(
      command, 'GKE Cluster Update to enable GCSFuse CSI driver', args
  )
  if return_code != 0:
    xpk_print(f'GKE Cluster Update request returned ERROR {return_code}')
    return 1
  return 0


def upgrade_gke_control_plane_version(args, default_rapid_gke_version) -> int:
  """Upgrade GKE cluster's control plane version before updating nodepools to use CloudDNS.

  Args:
    args: user provided arguments for running the command.
    default_rapid_gke_version: Rapid default version for the upgrade.

  Returns:
    0 if successful and 1 otherwise.
  """
  command = (
      'gcloud container clusters upgrade'
      f' {args.cluster} --project={args.project}'
      f' --region={zone_to_region(args.zone)}'
      f' --cluster-version={default_rapid_gke_version}'
      ' --master'
      ' --quiet'
  )
  xpk_print("Updating GKE cluster's control plane version, may take a while!")
  return_code = run_command_with_updates(
      command,
      'GKE Cluster control plane version update to enable Cloud DNS',
      args,
  )
  if return_code != 0:
    xpk_print(
        "GKE cluster's control plane version update request returned"
        f' ERROR {return_code}'
    )
    return 1
  return 0


def upgrade_gke_nodepools_version(args, default_rapid_gke_version) -> int:
  """Upgrade nodepools in the cluster to default rapid gke version. Recreates the nodes.

  Args:
    args: user provided arguments for running the command.
    default_rapid_gke_version: Rapid default version for the upgrade.

  Returns:
    0 if successful and 1 otherwise.
  """
  existing_node_pool_names, return_code = get_all_nodepools_programmatic(args)
  if return_code != 0:
    xpk_print('Listing all node pools failed!')
    return return_code

  # Batch execution to upgrade node pools simultaneously
  commands = []
  task_names = []
  for node_pool_name in existing_node_pool_names:
    commands.append(
        'gcloud container clusters upgrade'
        f' {args.cluster} --project={args.project}'
        f' --region={zone_to_region(args.zone)}'
        f' --cluster-version={default_rapid_gke_version}'
        f' --node-pool={node_pool_name}'
        ' --quiet'
    )
    task_names.append(f'Upgrading node pool {node_pool_name}.')

  for i, command in enumerate(commands):
    xpk_print(f'To complete {task_names[i]} we are executing {command}')
  max_return_code = run_commands(
      commands, 'Update GKE node pools to default RAPID GKE version', task_names
  )
  if max_return_code != 0:
    xpk_print(
        'GKE node pools update to default RAPID GKE version returned ERROR:'
        f' {max_return_code}'
    )
    return max_return_code
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
  num_networks = 5 if system.device_type == h100_device_type else 9
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
  yml_string = cluster_network_yaml.format(cluster_name=args.cluster)
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


def print_reservations(args) -> int:
  """Print the reservations in the project.

  Args:
    args: user provided arguments for running the command.

  Returns:
    0 if successful and 1 otherwise.
  """
  command = f'gcloud beta compute reservations list --project={args.project}'
  return_code = run_command_with_updates(
      command, 'Get all reservations in the project', args
  )
  if return_code != 0:
    xpk_print(f'Get all reservations returned ERROR {return_code}')
    return 1
  return 0


def verify_reservation_exists(args) -> int:
  """Verify the reservation exists.

  Args:
    args: user provided arguments for running the command.

  Returns:
    0 if successful and 1 otherwise.
  """
  command = (
      f'gcloud beta compute reservations describe {args.reservation}'
      f' --project={args.project} --zone={args.zone}'
  )
  return_code = run_command_with_updates(command, 'Describe reservation', args)
  if return_code != 0:
    xpk_print(f'Describe reservation returned ERROR {return_code}')
    xpk_print('Please confirm that your reservation name is correct.')
    return 1
  return 0


def get_capacity_type(args) -> tuple[CapacityType, int]:
  """Determine the capacity type based on user arguments.

  Args:
    args: user provided arguments for running the command.

  Returns:
    Tuple with string with the system characteristics and
    int of 0 if successful and 1 otherwise.
  """
  capacity_type = CapacityType.UNKNOWN
  num_types = 0
  return_code = 0

  # Determine the capacity argument.
  if args.on_demand:
    capacity_type = CapacityType.ON_DEMAND
    num_types += 1
  if args.reservation:
    return_code = verify_reservation_exists(args)
    if return_code > 0:
      return capacity_type, return_code
    capacity_type = CapacityType.RESERVATION
    num_types += 1
  if args.spot:
    capacity_type = CapacityType.SPOT
    num_types += 1

  # Check that the number of user arguments provided is valid.
  if num_types == 0:
    capacity_type = CapacityType.UNKNOWN
  elif num_types != 1:
    xpk_print(
        'ERROR: User specified more than one of the following arguments. Please'
        ' specify only one of `--reservation=$RESERVATION_NAME`, `--on-demand`'
        ' or `--spot`.'
    )
    return_code = 1

  return capacity_type, return_code


def get_capacity_arguments_from_capacity_type(
    args, capacity_type: CapacityType
) -> tuple[str, int]:
  """Determine the TPU Nodepool creation capacity arguments needed.

  Args:
    args: user provided arguments for running the command.
    capacity_type: The type of capacity the user configured.

  Returns:
    Tuple with string with the capacity argument to use and
    int of 0 if successful and 1 otherwise.
  """
  capacity_args = ''
  return_code = 0

  match capacity_type:
    case CapacityType.ON_DEMAND:
      capacity_args = ''
    case CapacityType.SPOT:
      capacity_args = '--spot'
    case CapacityType.RESERVATION:
      capacity_args = (
          f'--reservation-affinity=specific --reservation={args.reservation}'
      )
    case _:
      xpk_print(
          f'Unknown capacity type: {capacity_type}. Unable to determine'
          ' capacity args.'
      )
      return_code = 1
  return capacity_args, return_code


def get_capacity_node_selectors_from_capacity_type(
    args, capacity_type: str
) -> tuple[str, int]:
  """Determine the node selectors for a workload to run on a specific capacity type.

  Args:
    args: user provided arguments for running the command.
    capacity_type: The type of capacity the user configured.

  Returns:
    Tuple with string with the node selectors to use and
    int of 0 if successful and 1 otherwise.
  """
  node_selector = ''
  return_code = 0

  match capacity_type:
    case CapacityType.ON_DEMAND.name:
      node_selector = ''
    case CapacityType.SPOT.name:
      node_selector = 'cloud.google.com/gke-spot="true"'
    case CapacityType.RESERVATION.name:
      node_selector = f'cloud.google.com/reservation-name: {args.reservation}'
    case _:
      xpk_print(
          f'Unknown capacity type: {capacity_type}. Unable to determine the'
          ' node selectors.'
      )
      return_code = 1
  return node_selector, return_code


def create_or_update_cluster_configmap(configmap_yml: dict) -> int:
  """
  Args:
    configmap_yml: dict containing ConfigMap name and yml string.

  Returns:
    0 if successful, 1 otherwise.
  """
  commands = []
  task_names = []
  for configmap_name, yml_string in configmap_yml.items():
    tmp = write_tmp_file(yml_string)
    command = f'kubectl apply -f {str(tmp.file.name)}'
    commands.append(command)
    task_name = f'ConfigMap CreateOrUpdate-{configmap_name}'
    task_names.append(task_name)

  return_code = run_commands(
      commands, 'GKE Cluster CreateOrUpdate ConfigMap(s)', task_names
  )
  if return_code != 0:
    xpk_print(
        'GKE Cluster Create/Update ConfigMap(s) request returned ERROR'
        f' {return_code}'
    )
    return 1
  return 0


def create_cluster_configmaps(
    args,
    system,
    tensorboard_config: dict,
    autoprovisioning_config: AutoprovisioningConfig | None,
) -> int:
  """Run the Create GKE Cluster ConfigMap request.

  Args:
    args: user provided arguments for running the command.
    system: system characteristics.
    tensorboard_config: map that contains Vertex Tensorboard name, id and location
    autoprovisioning_config: Config used in autoprovisioning.
  Returns:
    0 if successful and 1 otherwise.
  """
  configmap_yml = {}

  # ConfigMap to store resources available in the cluster.
  device_type = system.device_type
  if system.accelerator_type == AcceleratorType['GPU']:
    resources_data = f'{device_type}: "{int(args.num_nodes)}"'
  elif (
      not args.enable_pathways
      and args.enable_autoprovisioning
      and autoprovisioning_config
  ):
    # Currently autoprovisioning is not supported with Pathways.
    # Auto provisioning will have variable topologies for a gke accelerator type.
    resources_data = (
        f'{system.gke_accelerator}: {AUTOPROVISIONING_CONFIG_VALUE}'
    )
    resources_data += (
        f'\n  {AUTOPROVISIONING_CONFIG_MINIMUM_KEY}:'
        f' "{autoprovisioning_config.minimum_chips}"'
    )
    resources_data += (
        f'\n  {AUTOPROVISIONING_CONFIG_MAXIMUM_KEY}:'
        f' "{autoprovisioning_config.maximum_chips}"'
    )
  else:
    resources_data = (
        f'{device_type}: "{int(args.num_slices) * system.vms_per_slice}"'
    )
  resources_configmap_name = f'{args.cluster}-{CLUSTER_RESOURCES_CONFIGMAP}'
  resources_yml = cluster_configmap_yaml.format(
      args=args, name=resources_configmap_name, data=resources_data
  )
  configmap_yml[resources_configmap_name] = resources_yml

  # ConfigMap to store cluster metadata.
  # XPK Version.
  metadata = f'xpk_version: {xpk_current_version}'
  # Vertex Tensorboard information
  for key, value in tensorboard_config.items():
    metadata += f'\n  {key}: "{value}"'
  # Capacity Type.
  capacity_type, return_code = get_capacity_type(args)
  if return_code != 0:
    xpk_print('Unable to determine capacity type.')
    return return_code
  metadata += f'\n  {CAPACITY_TYPE_CONFIG_KEY}: {capacity_type.name}'
  # Reservation ID if applicable.
  if capacity_type == CapacityType.RESERVATION:
    metadata += f'\n  {RESERVATION_CONFIG_KEY}: {args.reservation}'
  metadata_configmap_name = f'{args.cluster}-{CLUSTER_METADATA_CONFIGMAP}'
  metadata_yml = cluster_configmap_yaml.format(
      args=args, name=metadata_configmap_name, data=metadata
  )
  configmap_yml[metadata_configmap_name] = metadata_yml
  return create_or_update_cluster_configmap(configmap_yml)


def get_cluster_configmap(args, configmap_name) -> dict[str, str] | None:
  """Run the Get GKE Cluster ConfigMap request.

  Args:
    args: user provided arguments for running the command.
    configmap_name: name of the configmap.

  Returns:
    key:value pairs stored in cluster ConfigMap.
  """
  command = (
      'kubectl get configmap'
      f' {configmap_name} -o=custom-columns="ConfigData:data" --no-headers=true'
  )

  return_code, return_value = run_command_for_value(
      command, 'GKE Cluster Get ConfigMap', args
  )
  if return_code != 0:
    xpk_print(f'GKE Cluster Get ConfigMap request returned ERROR {return_code}')
    return None

  config_map = {}
  return_value = return_value.strip()

  if return_value:
    # Format of ConfigMap: map[key1:value1 key2:value2]
    return_value = return_value[return_value.index('map') :]
    configs = return_value[4:-1].split(' ')

    for config in configs:
      key, value = config.strip().split(':')
      config_map[key] = value
  return config_map


def create_vertex_tensorboard(args) -> dict:
  """Creates a Tensorboard instance in Vertex AI.

  Args:
    args: user provided arguments.

  Returns:
    dict containing Tensorboard instance name, id and location.
  """
  from cloud_accelerator_diagnostics import tensorboard  # pylint: disable=import-outside-toplevel

  tensorboard_config = {}
  tensorboard_name = args.tensorboard_name
  if tensorboard_name is None:
    tensorboard_name = f'{args.cluster}-{DEFAULT_VERTEX_TENSORBOARD_NAME}'
  instance_id = tensorboard.create_instance(  # pylint: disable=used-before-assignment
      project=args.project,
      location=args.tensorboard_region,
      tensorboard_name=tensorboard_name,
  )
  if instance_id:
    xpk_print(
        f'Tensorboard instance {tensorboard_name} is successfully created.'
    )
    tensorboard_config['tensorboard_region'] = args.tensorboard_region
    tensorboard_config['tensorboard_name'] = tensorboard_name
    tensorboard_config['tensorboard_id'] = instance_id
  return tensorboard_config


def create_vertex_experiment(args) -> dict:
  """Creates an Experiment in Vertex AI.

  Args:
    args: user provided arguments.

  Returns:
    map containing Vertex Tensorboard configurations.
  """
  from cloud_accelerator_diagnostics import tensorboard  # pylint: disable=import-outside-toplevel

  metadata_configmap_name = f'{args.cluster}-{CLUSTER_METADATA_CONFIGMAP}'
  cluster_config_map = get_cluster_configmap(args, metadata_configmap_name)

  if cluster_config_map is None or 'tensorboard_name' not in cluster_config_map:
    xpk_print(
        'No Vertex Tensorboard instance has been created in cluster create. Run'
        ' `xpk cluster create --create-vertex-tensorboard` before running `xpk'
        ' workload create --use-vertex-tensorboard` to create a Vertex'
        ' Tensorboard instance. Alternatively, use `xpk cluster create-pathways'
        ' --create-vertex-tensorboard` before running `xpk workload'
        ' create-pathways --use-vertex-tensorboard`.'
    )
    return None

  tensorboard_config = {}
  tensorboard_config['tensorboard_project'] = args.project
  tensorboard_config['tensorboard_region'] = cluster_config_map[
      'tensorboard_region'
  ]
  tensorboard_config['tensorboard_name'] = cluster_config_map[
      'tensorboard_name'
  ]
  experiment_name = args.experiment_name
  if experiment_name is None:
    experiment_name = f'{args.cluster}-{args.workload}'
  tensorboard_config['experiment_name'] = experiment_name

  _, tensorboard_url = tensorboard.create_experiment(
      project=args.project,
      location=tensorboard_config['tensorboard_region'],
      experiment_name=experiment_name,
      tensorboard_name=tensorboard_config['tensorboard_name'],
  )
  if tensorboard_url is None:
    return None

  xpk_print(f'You can view Vertex Tensorboard at: {tensorboard_url}')
  return tensorboard_config


def get_all_clusters_programmatic(args) -> tuple[list[str], int]:
  """Gets all the clusters associated with the project / region.

  Args:
    args: user provided arguments for running the command.

  Returns:
    List of cluster names and 0 if successful and 1 otherwise.
  """
  command = (
      'gcloud container clusters list'
      f' --project={args.project} --region={zone_to_region(args.zone)}'
      ' --format="csv[no-heading](name)"'
  )
  return_code, raw_cluster_output = run_command_for_value(
      command, 'Find if Cluster Exists', args
  )
  if return_code != 0:
    xpk_print(f'Find if Cluster Exists returned ERROR {return_code}')
    return [], return_code

  return raw_cluster_output.splitlines(), 0


def is_cluster_using_clouddns(args) -> bool:
  """Checks if cluster is using CloudDNS.
  Args:
    args: user provided arguments for running the command.

  Returns:
    True if cluster is using CloudDNS and False otherwise.
  """
  command = (
      f'gcloud container clusters describe {args.cluster}'
      f' --project={args.project} --region={zone_to_region(args.zone)}'
      ' | grep "clusterDns: CLOUD_DNS" | wc -l'
  )
  return_code, cloud_dns_matches = run_command_for_value(
      command,
      'Check if Cloud DNS is enabled in cluster describe.',
      args,
  )
  if return_code != 0:
    xpk_exit(return_code)
  cloud_dns_matches = int(cloud_dns_matches)
  if cloud_dns_matches > 0:
    xpk_print('Cloud DNS is enabled on the cluster, no update needed.')
    return True
  return False


def is_workload_identity_enabled_on_cluster(args) -> bool:
  """Checks if Workload Identity Federation is enabled on the cluster.
  Args:
    args: user provided arguments for running the command.
  Returns:
    True if Workload Identity Federation is enabled on the cluster and False otherwise.
  """
  command = (
      f'gcloud container clusters describe {args.cluster}'
      f' --project={args.project} --region={zone_to_region(args.zone)}'
      ' --format="value(workloadIdentityConfig.workloadPool)"'
  )
  return_code, workload_pool = run_command_for_value(
      command,
      'Checks if Workload Identity Federation is enabled in cluster describe.',
      args,
  )
  if return_code != 0:
    xpk_exit(return_code)
  if workload_pool == f'{args.project}.svc.id.goog':
    xpk_print(
        'Workload Identity Federation is enabled on the cluster, no update'
        ' needed.'
    )
    return True
  return False


def is_gcsfuse_driver_enabled_on_cluster(args) -> bool:
  """Checks if GCSFuse CSI driver is enabled on the cluster.
  Args:
    args: user provided arguments for running the command.
  Returns:
    True if GCSFuse CSI driver is enabled on the cluster and False otherwise.
  """
  command = (
      f'gcloud container clusters describe {args.cluster}'
      f' --project={args.project} --region={zone_to_region(args.zone)}'
      ' --format="value(addonsConfig.gcsFuseCsiDriverConfig.enabled)"'
  )
  return_code, gcsfuse_driver_enabled = run_command_for_value(
      command,
      'Checks if GCSFuse CSI driver is enabled in cluster describe.',
      args,
  )
  if return_code != 0:
    xpk_exit(return_code)
  if gcsfuse_driver_enabled.lower() == 'true':
    xpk_print('GCSFuse CSI driver is enabled on the cluster, no update needed.')
    return True
  return False


def update_cluster_with_clouddns_if_necessary(args) -> int:
  """Updates a GKE cluster to use CloudDNS, if not enabled already.

  Args:
    args: user provided arguments for running the command.

  Returns:
    0 if successful and error code otherwise.
  """
  all_clusters, return_code = get_all_clusters_programmatic(args)
  if return_code > 0:
    xpk_print('Listing all clusters failed!')
    return 1
  if args.cluster in all_clusters:
    # If cluster is already using clouddns, no update necessary!
    if is_cluster_using_clouddns(args):
      return 0
    cluster_update_return_code = update_gke_cluster_with_clouddns(args)
    if cluster_update_return_code > 0:
      xpk_print('Updating GKE cluster to use CloudDNS failed!')
      return cluster_update_return_code

    # Find default rapid control plane version and update the control plane to the same.
    server_config_return_code, gke_server_config = get_gke_server_config(args)
    if server_config_return_code != 0:
      xpk_exit(server_config_return_code)
    upgrade_master_return_code = upgrade_gke_control_plane_version(
        args, gke_server_config.default_rapid_gke_version
    )
    if upgrade_master_return_code > 0:
      xpk_print("Updating GKE cluster's control plane upgrade failed!")
      return upgrade_master_return_code

    # Upgrade nodepools version after the master upgrade.
    node_pool_update_code = upgrade_gke_nodepools_version(
        args, gke_server_config.default_rapid_gke_version
    )
    if node_pool_update_code > 0:
      xpk_print('Upgrading nodepools version failed!')
      return node_pool_update_code
  return 0


def update_cluster_with_workload_identity_if_necessary(args) -> int:
  """Updates a GKE cluster to enable Workload Identity Federation, if not enabled already.
  Args:
    args: user provided arguments for running the command.
  Returns:
    0 if successful and error code otherwise.
  """

  if is_workload_identity_enabled_on_cluster(args):
    return 0
  cluster_update_return_code = (
      update_gke_cluster_with_workload_identity_enabled(args)
  )
  if cluster_update_return_code > 0:
    xpk_print(
        'Updating GKE cluster to enable Workload Identity Federation failed!'
    )
    return cluster_update_return_code

  return 0


def update_cluster_with_gcsfuse_driver_if_necessary(args) -> int:
  """Updates a GKE cluster to enable GCSFuse CSI driver, if not enabled already.
  Args:
    args: user provided arguments for running the command.
  Returns:
    0 if successful and error code otherwise.
  """

  if is_gcsfuse_driver_enabled_on_cluster(args):
    return 0
  cluster_update_return_code = update_gke_cluster_with_gcsfuse_driver_enabled(
      args
  )
  if cluster_update_return_code > 0:
    xpk_print('Updating GKE cluster to enable GCSFuse CSI driver failed!')
    return cluster_update_return_code

  return 0


def get_nodepool_zone(args, nodepool_name) -> tuple[int, str]:
  """Return zone in which nodepool exists in the cluster.

  Args:
    args: user provided arguments for running the command.
    nodepool_name: name of nodepool.

  Returns:
    Tuple of int, str where
    int is the return code - 0 if successful, 1 otherwise.
    str is the zone of nodepool.
  """
  command = (
      f'gcloud beta container node-pools describe {nodepool_name}'
      f' --cluster {args.cluster} --project={args.project}'
      f' --region={zone_to_region(args.zone)} --format="value(locations)"'
  )
  return_code, nodepool_zone = run_command_for_value(
      command, 'Get Node Pool Zone', args
  )
  if return_code != 0:
    xpk_print(f'Get Node Pool Zone returned ERROR {return_code}')
    return 1, None

  return 0, nodepool_zone.strip()


def get_nodepool_workload_metadata_mode(args, nodepool_name) -> tuple[int, str]:
  """Return Workload Identity metadata mode of the nodepool.
  Args:
    args: user provided arguments for running the command.
    nodepool_name: name of nodepool.
  Returns:
    Tuple of int, str where
    int is the return code - 0 if successful, 1 otherwise.
    str is the workload metadata mode of nodepool.
  """
  command = (
      f'gcloud beta container node-pools describe {nodepool_name}'
      f' --cluster {args.cluster} --project={args.project}'
      f' --region={zone_to_region(args.zone)} --format="value(config.workloadMetadataConfig.mode)"'
  )
  return_code, nodepool_WI_mode = run_command_for_value(
      command, 'Get Node Pool Workload Identity Metadata Mode', args
  )
  if return_code != 0:
    xpk_print(
        'Get Node Pool Workload Identity Metadata Mode returned ERROR'
        f' {return_code}'
    )
    return 1, None

  return 0, nodepool_WI_mode.strip()


def check_cluster_resources(args, system) -> tuple[bool, bool]:
  """Check if cluster has resources of a specified device_type/gke_accelerator.
  This check will be skipped if <args.cluster>-<_CLUSTER_RESOURCES_CONFIGMAP> ConfigMap doesn't exist for the cluster.

  Args:
    args: user provided arguments for running the command.
    system: system characteristics.

  Returns:
    Tuple of bool, bool
    True if resources in the cluster should be checked, False otherwise.
    True if device_type/gke_accelerator exists in the cluster, False otherwise.
  """
  resources_configmap_name = f'{args.cluster}-{CLUSTER_RESOURCES_CONFIGMAP}'
  resources_config_map = get_cluster_configmap(args, resources_configmap_name)
  if resources_config_map is None:
    xpk_print(
        f'No ConfigMap exist for cluster with the name {resources_config_map}.'
        ' Cluster resources check will be skipped.'
    )
    return False, False
  if system.device_type in resources_config_map:
    return True, True
  elif system.gke_accelerator in resources_config_map:
    return True, True
  return True, False


def get_all_nodepools_programmatic(args) -> tuple[list[str], int]:
  """Gets all the nodepools associated with the cluster / project / region.

  Args:
    args: user provided arguments for running the command.

  Returns:
    List of nodepools and 0 if successful and 1 otherwise.
  """
  command = (
      'gcloud beta container node-pools list'
      ' --cluster'
      f' {args.cluster} --project={args.project} --region={zone_to_region(args.zone)}'
      ' --format="csv[no-heading](name)"'
  )
  return_code, raw_nodepool_output = run_command_for_value(
      command, 'Get All Node Pools', args
  )
  if return_code != 0:
    xpk_print(f'Get All Node Pools returned ERROR {return_code}')
    return [], 1

  return raw_nodepool_output.splitlines(), 0


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


def get_node_pools_to_delete(
    args, system, existing_node_pool_names, desired_node_pool_names
) -> list:
  """Get list of nodepools to delete from the cluster.

  Args:
    args: user provided arguments for running the command.
    system: system characteristics.
    existing_node_pool_names: names of nodepools that already exist in the cluster.
    desired_node_pool_names: names of nodepools that should exist in the cluster.

  Returns:
    List of nodepool names to delete.
  """
  node_pools_to_delete = []
  check_resource, is_requested_resource_in_cluster = check_cluster_resources(
      args, system
  )
  for existing_node_pool_name in existing_node_pool_names:
    # Deletion logic would leave behind any Pathways CPU nodepools.
    if existing_node_pool_name.find(f'{args.cluster}-np-') != 0:
      continue

    # Nodepools will be deleted in two scenarios:
    # Scenario 1: Cluster exists with 3 nodepools of 'x' device_type/gke_accelerator and now we are updating
    # the cluster to 2 nodepools of 'x' device_type/gke_accelerator. In this case, we will delete
    # '{args.cluster}-np-2' from the cluster.
    # Scenario 2: Cluster exists with 2 nodepools of 'x' device_type/gke_accelerator and now we are updating
    # the cluster to 2 nodepools of 'y' device_type/gke_accelerator. In this case, we will delete
    # '{args.cluster}-np-0' and '{args.cluster}-np-1' from the cluster.
    if existing_node_pool_name not in desired_node_pool_names or (
        check_resource and not is_requested_resource_in_cluster
    ):
      node_pools_to_delete.append(existing_node_pool_name)

  return node_pools_to_delete


def run_gke_node_pool_create_command(
    args, system, gke_node_pool_version
) -> int:
  """Run the Create GKE Node Pool request.

  Args:
    args: user provided arguments for running the command.
    system: System characteristics based on device type/topology.
    gke_node_pool_version: GKE version to use to create node pools.

  Returns:
    0 if successful and 1 otherwise.
  """
  device_type = args.tpu_type if args.tpu_type else args.device_type
  xpk_print(
      f'Creating {args.num_slices} node pool or pools of {device_type}\n'
      f'We assume that the underlying system is: {system}'
  )
  existing_node_pool_names, return_code = get_all_nodepools_programmatic(args)
  if return_code > 0:
    xpk_print('Listing all node pools failed!')
    return return_code

  capacity_type, return_code = get_capacity_type(args)
  if return_code > 0:
    xpk_print('Parsing capacity type failed!')
    return return_code
  if capacity_type == CapacityType.UNKNOWN:
    return_code = print_reservations(args)
    xpk_print(
        'ERROR: User needs to provide the capacity type. Please specify one of'
        ' the following `--reservation=$RESERVATION_NAME`, `--on-demand`'
        ' or `--spot`. See the above list of reservations to choose from.'
    )
    if return_code > 0:
      xpk_print('Listing all reservations failed!')
    return_code = 1
  capacity_args, return_code = get_capacity_arguments_from_capacity_type(
      args, capacity_type
  )
  if return_code > 0:
    xpk_print('Parsing capacity arguments failed!')
    return return_code

  if system.accelerator_type == AcceleratorType['GPU']:
    xpk_print(
        f'Creating 1 node pool with {args.num_nodes} nodes of'
        f' {system.device_type}\nUnderlyingly, we assume that means: {system}'
    )
    desired_node_pool_names = [f'{args.cluster}-np-0']
  else:
    xpk_print(
        f'Creating {args.num_slices} node pool or pools of'
        f' {system.device_type}\nUnderlyingly, we assume that means: {system}'
    )
    desired_node_pool_names = [
        f'{args.cluster}-np-{slice_num}' for slice_num in range(args.num_slices)
    ]

  node_pools_to_remain = []
  delete_commands = []
  delete_task_names = []
  node_pools_to_update_WI = []
  update_WI_commands = []
  update_WI_task_names = []
  if existing_node_pool_names:
    return_code, existing_node_pool_zone = get_nodepool_zone(
        args, existing_node_pool_names[0]
    )
    if return_code != 0:
      return 1

    if existing_node_pool_zone and existing_node_pool_zone != args.zone:
      xpk_print(
          f'Cluster {args.cluster} already has nodepools in zone:'
          f' {existing_node_pool_zone}. Use the same zone to update nodepools'
          ' in the cluster.'
      )
      return 1

    node_pools_to_delete = get_node_pools_to_delete(
        args, system, existing_node_pool_names, desired_node_pool_names
    )
    for node_pool_name in existing_node_pool_names:
      if node_pool_name.find(f'{args.cluster}-np-') != 0:
        continue

      if node_pool_name in node_pools_to_delete:
        command = (
            'gcloud beta container node-pools delete'
            f' {node_pool_name} --cluster={args.cluster}'
            f' --zone={zone_to_region(args.zone)}'
            f' --project={args.project} --quiet'
        )
        task = f'NodepoolDelete-{node_pool_name}'
        delete_commands.append(command)
        delete_task_names.append(task)
      else:
        node_pools_to_remain.append(node_pool_name)

    # Workload Identity for existing nodepools
    if args.enable_workload_identity or args.enable_gcsfuse_csi_driver:
      for node_pool_name in existing_node_pool_names:
        if not node_pool_name in node_pools_to_delete:
          # Check if workload identity is not already enabled:
          return_code, existing_node_pool_medadata_mode = (
              get_nodepool_workload_metadata_mode(args, node_pool_name)
          )
          if return_code != 0:
            return 1

          if (
              existing_node_pool_zone
              and existing_node_pool_medadata_mode != 'GKE_METADATA'
          ):
            command = (
                'gcloud container node-pools update'
                f' {node_pool_name} --cluster={args.cluster}'
                f' --zone={zone_to_region(args.zone)}'
                f' --project={args.project} --quiet'
                ' --workload-metadata=GKE_METADATA'
            )
            task = (
                'Update nodepool with Workload Identity enabled'
                f' {node_pool_name}'
            )
            update_WI_commands.append(command)
            update_WI_task_names.append(task)
            node_pools_to_update_WI.append(node_pool_name)

  # Deletion of nodepools should happen before attempting to create new nodepools for the case
  # when cluster is getting updated from 'x' device_type/gke_accelerator to 'y' device_type/gke_accelerator.
  # In that case, '{args.cluster}-np-i' nodepool will be re-created for 'y' device_type/gke_accelerator.
  if delete_commands:
    will_delete = True
    if node_pools_to_delete and not args.force:
      will_delete = get_user_input(
          f'Planning to delete {len(node_pools_to_delete)} node pools including'
          f' {node_pools_to_delete}. \nDo you wish to delete: y (yes) / n'
          ' (no):\n'
      )
    if not will_delete:
      xpk_print(
          'You have requested to not delete the existing nodepools in the'
          ' cluster. There will be no change to the cluster.'
      )
      return 1

    for i, command in enumerate(delete_commands):
      xpk_print(
          f'To complete {delete_task_names[i]} we are executing {command}'
      )
    max_return_code = run_commands(
        delete_commands,
        'Delete Nodepools',
        delete_task_names,
        dry_run=args.dry_run,
    )
    if max_return_code != 0:
      xpk_print(f'Delete Nodepools returned ERROR {max_return_code}')
      return 1

  # Enable Workload Identity on existing Nodepools
  if update_WI_commands:
    will_update_WI = True
    if node_pools_to_update_WI and not args.force:
      will_update_WI = get_user_input(
          'Planning to enable Workload Identity Federation on'
          f' {len(node_pools_to_update_WI)} existing node pools including'
          f' {node_pools_to_update_WI}.This immediately enables Workload'
          ' Identity Federation for GKE for any workloads running in the node'
          ' pool. Also, xpk does not support disabling Workload Identity on'
          ' clusters that have it enabled already \nDo you wish to update: y'
          ' (yes) / n (no):\n'
      )
    if not will_update_WI:
      for i, command in enumerate(update_WI_commands):
        xpk_print(
            f'To complete {update_WI_task_names[i]} we are executing {command}'
        )
      max_return_code = run_commands(
          update_WI_commands,
          'Enable Workload Identity on existing Nodepools',
          update_WI_task_names,
          dry_run=args.dry_run,
      )
      if max_return_code != 0:
        xpk_print(
            'Enable Workload Identity on existing Nodepools returned ERROR'
            f' {max_return_code}'
        )
        return 1

    # Update {args.cluster}-{_CLUSTER_RESOURCES_CONFIGMAP} ConfigMap to 'y': '0'
    # and remove 'x' from the ConfigMap when cluster is getting updated from
    # 'x' device_type/gke_accelerator to 'y' device_type/gke_accelerator.
    if not node_pools_to_remain:
      if args.enable_autoprovisioning:
        resources_data = (
            f'{system.gke_accelerator}: {AUTOPROVISIONING_CONFIG_VALUE}'
        )
      else:
        resources_data = f'{device_type}: "0"'
      resources_configmap_name = f'{args.cluster}-{CLUSTER_RESOURCES_CONFIGMAP}'
      resources_yml = cluster_configmap_yaml.format(
          args=args, name=resources_configmap_name, data=resources_data
      )
      configmap_yml = {}
      configmap_yml[resources_configmap_name] = resources_yml
      return_code = create_or_update_cluster_configmap(configmap_yml)
      if return_code != 0:
        return 1

  create_commands = []
  create_task_names = []
  for node_pool_name in desired_node_pool_names:
    if node_pool_name in node_pools_to_remain:
      continue
    command = (
        'gcloud beta container node-pools create'
        f' {node_pool_name}'
        f' --region={zone_to_region(args.zone)}'
        f' --cluster={args.cluster}'
        f' --project={args.project} --node-locations={args.zone}'
        f' --machine-type={system.gce_machine_type}'
        f' --host-maintenance-interval={args.host_maintenance_interval}'
        f' {capacity_args}'
        ' --enable-gvnic'
        f' {args.custom_nodepool_arguments}'
    )
    if system.accelerator_type == AcceleratorType['TPU']:
      command += f' --node-version={gke_node_pool_version}'
      command += f' --num-nodes={system.vms_per_slice}'
      command += ' --placement-type=COMPACT  --max-pods-per-node 15'
      command += (
          ' --scopes=storage-full,gke-default,"https://www.googleapis.com/auth/cloud-platform"'
      )
      command += f' --tpu-topology={system.topology}'
      command += f' {args.custom_tpu_nodepool_arguments}'
    elif system.accelerator_type == AcceleratorType['GPU']:
      subnet_prefix = f'{args.cluster}-{zone_to_region(args.zone)}'
      command += f' --num-nodes={args.num_nodes}'
      command += (
          ' --accelerator'
          f' type={system.gke_accelerator},count={str(system.chips_per_vm)},gpu-driver-version=latest'
          ' --no-enable-autoupgrade '
          ' --scopes="https://www.googleapis.com/auth/cloud-platform"'
          ' --additional-node-network'
          f' network={args.cluster}-net-1,subnetwork={subnet_prefix}-sub-1'
          ' --additional-node-network'
          f' network={args.cluster}-net-2,subnetwork={subnet_prefix}-sub-2'
          ' --additional-node-network'
          f' network={args.cluster}-net-3,subnetwork={subnet_prefix}-sub-3'
          ' --additional-node-network'
          f' network={args.cluster}-net-4,subnetwork={subnet_prefix}-sub-4'
      )
      if device_type == h100_mega_device_type:
        command += (
            ' --additional-node-network'
            f' network={args.cluster}-net-5,subnetwork={subnet_prefix}-sub-5'
            ' --additional-node-network'
            f' network={args.cluster}-net-6,subnetwork={subnet_prefix}-sub-6'
            ' --additional-node-network'
            f' network={args.cluster}-net-7,subnetwork={subnet_prefix}-sub-7'
            ' --additional-node-network'
            f' network={args.cluster}-net-8,subnetwork={subnet_prefix}-sub-8'
            ' --max-pods-per-node=32'
        )
    elif system.accelerator_type == AcceleratorType['CPU']:
      command += f' --num-nodes={system.vms_per_slice}'
      command += ' --scopes=storage-full,gke-default'

    if args.enable_workload_identity or args.enable_gcsfuse_csi_driver:
      command += ' --workload-metadata=GKE_METADATA'

    task = f'NodepoolCreate-{node_pool_name}'
    create_commands.append(command)
    create_task_names.append(task)

  desired_pw_cpu_node_pools = ['cpu-user-np', 'cpu-rm-np', 'cpu-proxy-np']
  if args.enable_pathways:
    # Pathways needs CPU nodepools in addition to TPU nodepools
    for node_pool_name in desired_pw_cpu_node_pools:
      if node_pool_name in existing_node_pool_names:
        continue
      command = (
          'gcloud beta container node-pools create'
          f' {node_pool_name} --node-version={gke_node_pool_version}'
          f' --cluster={args.cluster}'
          f' --project={args.project} --node-locations={args.zone}'
          f' --region={zone_to_region(args.zone)}'
          ' --num-nodes=1'
          f' --machine-type={args.pathways_gce_machine_type}'
          ' --scopes=storage-full,gke-default'
          ' --enable-autoscaling --min-nodes=1 --max-nodes=20'
      )
      task = f'NodepoolCreate-{node_pool_name}'
      create_commands.append(command)
      create_task_names.append(task)

  for i, command in enumerate(create_commands):
    xpk_print(f'To complete {create_task_names[i]} we are executing {command}')
  max_return_code = run_commands(
      create_commands,
      'Create Nodepools',
      create_task_names,
      dry_run=args.dry_run,
  )
  if max_return_code != 0:
    xpk_print(f'Create Nodepools returned ERROR {max_return_code}')
    return 1

  xpk_print('Create or delete node pool request complete.')
  return 0


# TODO(vbarr): Remove this function when jobsets gets enabled by default on
# GKE clusters.
def set_jobset_on_cluster(args) -> int:
  """Add jobset command on server side and ask user to verify it is created.

  Args:
    args: user provided arguments for running the command.

  Returns:
    0 if successful and 1 otherwise.
  """
  command = (
      'kubectl apply --server-side -f'
      ' https://github.com/kubernetes-sigs/jobset/releases/download/v0.4.0/manifests.yaml'
  )
  task = f'Install Jobset on {args.cluster}'
  return_code = run_command_with_updates_retry(command, task, args)

  if return_code != 0:
    xpk_print(f'{task} returned with ERROR {return_code}.\n')
    xpk_print(
        "This LIKELY means you're missing Kubernetes Permissions, you can"
        ' validate this by checking if the error references permission problems'
        ' such as `requires one of ["container.*"] permission(s)`. Follow our'
        ' readme:'
        ' https://github.com/google/xpk/blob/main/README.md#troubleshooting for'
        ' instructions on how to fix these permissions.'
    )
  return return_code


def install_nccl_on_cluster(args, system: SystemCharacteristics) -> int:
  """Install NCCL plugin on the cluster.

  Args:
    args: user provided arguments for running the command.
    system: system characteristics.

  Returns:
    0 if successful and 1 otherwise.
  """
  if system.device_type == h100_device_type:
    command = (
        'kubectl apply -f '
        # pylint: disable=line-too-long
        'https://raw.githubusercontent.com/GoogleCloudPlatform/container-engine-accelerators/master/gpudirect-tcpx/nccl-tcpx-installer.yaml'
    )
  else:
    command = (
        'kubectl apply -f '
        # pylint: disable=line-too-long
        'https://raw.githubusercontent.com/GoogleCloudPlatform/container-engine-accelerators/master/gpudirect-tcpxo/nccl-tcpxo-installer.yaml'
    )

  return_code = run_command_with_updates(
      command, 'Install NCCL Plugin On Cluster', args
  )

  if return_code != 0:
    xpk_print(
        f'Install NCCL Plugin On Cluster request returned ERROR {return_code}'
    )
    return 1

  return 0


@dataclass
class GkeServerConfig:
  """Stores the valid gke versions based on gcloud recommendations."""

  default_rapid_gke_version: str
  valid_versions: set[str]


def get_gke_server_config(args) -> tuple[int, GkeServerConfig | None]:
  """Determine the GKE versions supported by gcloud currently.

  Args:
    args: user provided arguments for running the command.

  Returns:
    Tuple of
    int: 0 if successful and 1 otherwise.
    GkeServerConfig: stores valid gke version to use in node pool and cluster.
  """
  base_command = (
      'gcloud container get-server-config'
      f' --project={args.project} --region={zone_to_region(args.zone)}'
  )
  default_rapid_gke_version_cmd = (
      base_command
      + ' --flatten="channels" --filter="channels.channel=RAPID"'
      ' --format="value(channels.defaultVersion)"'
  )
  valid_versions_cmd = (
      base_command
      + ' --flatten="channels" --filter="channels.channel=RAPID"'
      ' --format="value(channels.validVersions)"'
  )
  base_command_description = 'Determine server supported GKE versions for'

  server_config_commands_and_descriptions = [
      (
          default_rapid_gke_version_cmd,
          base_command_description + 'default rapid gke version',
      ),
      (
          valid_versions_cmd,
          base_command_description + 'valid versions',
      ),
  ]
  command_outputs = []

  for command, command_description in server_config_commands_and_descriptions:
    return_code, cmd_output = run_command_for_value(
        command,
        command_description,
        args,
        hide_error=True,
    )
    if return_code != 0:
      xpk_print(f'Unable to get server config for {command_description}.')
      return return_code, None
    command_outputs.append(cmd_output)

  return 0, GkeServerConfig(
      default_rapid_gke_version=command_outputs[0].strip(),
      valid_versions=set(command_outputs[1].split(';')),
  )


def get_gke_control_plane_version(
    args, gke_server_config: GkeServerConfig
) -> tuple[int, str | None]:
  """Determine gke control plane version for cluster creation.

  Args:
    args: user provided arguments for running the command.
    gke_server_config: holds valid gke versions and recommended default version.

  Returns:
    Tuple of
    int: 0 if successful and 1 otherwise.
    str: gke control plane version to use.
  """

  # Override with user provide gke version if specified.
  if args.gke_version is not None:
    master_gke_version = args.gke_version
  else:
    master_gke_version = gke_server_config.default_rapid_gke_version

  is_valid_version = master_gke_version in gke_server_config.valid_versions

  if not is_valid_version:
    xpk_print(
        f'Planned GKE Version: {master_gke_version}\n Valid Versions:'
        f'\n{gke_server_config.valid_versions}\nRecommended / Default GKE'
        f' Version: {gke_server_config.default_rapid_gke_version}'
    )
    xpk_print(
        f'Error: Planned GKE Version {master_gke_version} is not valid.'
        f'Checks failed: Is Version Valid: {is_valid_version}'
    )
    xpk_print(
        'Please select a gke version from the above list using --gke-version=x'
        ' argument or rely on the default gke version:'
        f' {gke_server_config.default_rapid_gke_version}'
    )
    return 1, None

  return 0, master_gke_version


def get_gke_node_pool_version(
    args, gke_server_config: GkeServerConfig
) -> tuple[int, str | None]:
  """Determine the gke node pool version for the node pool.

  Args:
    args: user provided arguments for running the command.
    gke_server_config: holds valid gke versions and recommended default version.

  Returns:
    Tuple of
    int: 0 if successful and 1 otherwise.
    str: gke control plane version to use.
  """

  # By default use the current gke master version for creating node pools.
  command_description = 'Determine current gke master version'
  command = (
      f'gcloud beta container clusters describe {args.cluster}'
      f' --region {zone_to_region(args.zone)} --project {args.project}'
      ' --format="value(currentMasterVersion)"'
  )

  return_code, current_gke_master_version = run_command_for_value(
      command, command_description, args
  )
  if return_code != 0:
    xpk_print(
        f'Unable to get server config for command: {command_description}.'
    )
    return return_code, None

  # Override with user provide gke version if specified.
  if args.gke_version is not None:
    node_pool_gke_version = args.gke_version
  else:
    node_pool_gke_version = current_gke_master_version.strip()

  is_supported_node_pool_version = (
      node_pool_gke_version in gke_server_config.valid_versions
  )
  # In rare cases, user's provided gke version may be invalid, but gke will return an error if so.
  # An example scenario is if the user provided gke version is greater than the master version.
  if not is_supported_node_pool_version:
    xpk_print(
        f'Planned node pool version {node_pool_gke_version} is not supported in'
        ' valid version'
        f' {gke_server_config.valid_versions}\nPlease adjust the gke version'
        ' using --gke-version=x or remove the arg and depend on xpk default of'
        f' {current_gke_master_version}'
    )
    return 1, None
  return 0, node_pool_gke_version


def validate_docker_image(docker_image, args) -> int:
  """Validates that the user provided docker image exists in your project.

  Args:
    docker_image: The docker image to verify.
    args: user provided arguments for running the command.

  Returns:
    0 if successful and 1 otherwise.
  """

  project = args.project

  if not any(repo in docker_image for repo in ['gcr.io', 'docker.pkg.dev']):
    return 0

  command = (
      f'gcloud container images describe {docker_image} --project {project}'
  )
  return_code = run_command_with_updates(
      command, 'Validate Docker Image', args, verbose=False
  )
  if return_code != 0:
    xpk_print(
        'Failed to validate your docker image, check that the docker image'
        f' exists. You may be able to find the {docker_image} in {project}.'
        ' If the docker image exists, the service account of this'
        ' project maybe be missing the permissions to access the docker image.'
    )
    return return_code
  else:
    return 0


def build_docker_image_from_base_image(args, verbose=True) -> tuple[int, str]:
  """Adds script dir to the base docker image and uploads the image.

  Args:
    args: user provided arguments for running the command.

  Returns:
    Tuple of:
      0 if successful and 1 otherwise.
      Name of the Docker image created.
  """

  # Pick a name for the docker image.
  docker_image_prefix = os.getenv('USER', 'unknown')
  docker_name = f'{docker_image_prefix}-runner'

  script_dir_dockerfile = """FROM {base_docker_image}

  # Set the working directory in the container
  WORKDIR /app

  # Copy all files from local workspace into docker container
  COPY . .

  WORKDIR /app
  """

  docker_file = script_dir_dockerfile.format(
      base_docker_image=args.base_docker_image,
  )
  tmp = write_tmp_file(docker_file)
  docker_build_command = (
      f'docker build -f {str(tmp.file.name)} -t {docker_name} {args.script_dir}'
  )
  xpk_print(f'Building {args.script_dir} into docker image.')
  return_code = run_command_with_updates(
      docker_build_command,
      'Building script_dir into docker image',
      args,
      verbose=verbose,
  )
  if return_code != 0:
    xpk_print(
        'Failed to add script_dir to docker image, check the base docker image.'
        f' You should be able to navigate to the URL {args.base_docker_image}'
        f' in {args.project}.'
    )
    xpk_exit(1)

  # Pick a randomly generated `tag_length` character docker tag.
  tag_length = 4
  tag_random_prefix = ''.join(
      random.choices(string.ascii_lowercase, k=tag_length)
  )
  tag_datetime = datetime.datetime.now().strftime('%Y-%m-%d-%H-%M-%S')
  tag_name = f'{tag_random_prefix}-{tag_datetime}'
  cloud_docker_image = f'gcr.io/{args.project}/{docker_name}:{tag_name}'
  xpk_print(f'Adding Docker Image: {cloud_docker_image} to {args.project}')

  # Tag the docker image.
  tag_docker_image_command = f'docker tag {docker_name} {cloud_docker_image}'
  return_code = run_command_with_updates(
      tag_docker_image_command, 'Tag Docker Image', args, verbose=verbose
  )
  if return_code != 0:
    xpk_print(
        f'Failed to tag docker image with tag: {tag_name}.'
        f' You should be able to navigate to the URL {cloud_docker_image} in'
        f' {args.project}.'
    )
    xpk_exit(1)

  # Upload image to Artifact Registry.
  upload_docker_image_command = f'docker push {cloud_docker_image}'
  return_code = run_command_with_updates(
      upload_docker_image_command, 'Upload Docker Image', args, verbose=verbose
  )
  if return_code != 0:
    xpk_print(
        'Failed to upload docker image.'
        f' You should be able to navigate to the URL {cloud_docker_image} in'
        f' {args.project}.'
    )
    xpk_exit(1)
  return return_code, cloud_docker_image


def check_if_workload_exists(args) -> bool:
  """Check if workload exists.

  Args:
     args: user provided arguments for running the command.

  Returns:
    returns true if workload exist, otherwise returns false.
  """
  columns = {
      'Jobset': '.metadata.ownerReferences[0].name',
  }

  s = ','.join([key + ':' + value for key, value in columns.items()])

  command = f"kubectl get workloads -o=custom-columns='{s}'"
  return_code, return_msg = run_command_for_value(
      command, 'Check if Workload Already Exists', args
  )

  if return_code != 0:
    xpk_print(f'List Job request returned ERROR {return_code}')
    xpk_exit(return_code)

  lines = return_msg.split('\n')
  new_workload_name = args.workload
  for line in lines:
    if line == new_workload_name:
      return True
  return False


def check_if_workload_can_schedule(args, system: SystemCharacteristics) -> bool:
  """Check if workload can schedule based on the cluster resources (tpu_type and maximum VM in cluster).

  Args:
    args: user provided arguments for running the command.
    system: system characteristics

  Returns:
    returns true if workload can schedule, otherwise returns false.
  """
  resources_configmap_name = f'{args.cluster}-{CLUSTER_RESOURCES_CONFIGMAP}'
  cluster_config_map = get_cluster_configmap(args, resources_configmap_name)

  # Prevents workload creation failure for existing clusters with no ConfigMap
  if cluster_config_map is None:
    xpk_print(
        'No ConfigMap exist for cluster with the name'
        f' {resources_configmap_name}.'
    )
    return True

  # Check for gke accelerator type:
  missing_gke_accelerator_type = False
  if system.gke_accelerator not in cluster_config_map:
    xpk_print(
        f'Gke Accelerator Type Check: {args.workload} is requesting'
        f' {system.gke_accelerator} but cluster only contains'
        f' {cluster_config_map.keys()}. '
    )
    missing_gke_accelerator_type = True
  elif (
      cluster_config_map[system.gke_accelerator]
      == AUTOPROVISIONING_CONFIG_VALUE
  ):
    # Run total chip check when in autoprovisioning mode.
    max_chips_in_cluster = int(
        cluster_config_map[AUTOPROVISIONING_CONFIG_MAXIMUM_KEY]
    )
    num_chips_in_workload = get_total_chips_requested_from_args(args, system)

    if num_chips_in_workload > max_chips_in_cluster:
      xpk_print(
          f'{args.workload} is requesting {num_chips_in_workload} chips but'
          f' the cluster {args.cluster} supports up to {max_chips_in_cluster}.'
          '  Resize the cluster to support more chips with'
          ' `xpk cluster create --autoprovisioning-max-chips=X ...`'
      )
      return False
    return True

  # Check for device type
  missing_device_type = False
  device_type = system.device_type
  if device_type not in cluster_config_map:
    xpk_print(
        f'Device Type Check: {args.workload} is requesting {device_type} but '
        f'cluster only contains {cluster_config_map.keys()}. '
    )
    missing_device_type = True

  if missing_device_type and missing_gke_accelerator_type:
    xpk_print(
        'Both Device Type and GKE Accelerator Type checks failed.'
        f' XPK will not create the workload {args.workload}.'
    )
    return False
  else:
    # Check if the size of the workload will fit in the cluster.
    max_vm_in_cluster = int(cluster_config_map[device_type])
    if system.accelerator_type == AcceleratorType['GPU']:
      vm_required_by_workload = args.num_nodes
    else:
      vm_required_by_workload = args.num_slices * system.vms_per_slice
    if vm_required_by_workload > max_vm_in_cluster:
      xpk_print(
          f'{args.workload} is requesting {args.num_slices} slice/slices of'
          f' {device_type}, which is {vm_required_by_workload} VMs, but the'
          f' cluster only contains {max_vm_in_cluster} VMs of {device_type}.'
          ' XPK will not create this workload.'
      )
      return False

  return True


def use_base_docker_image_or_docker_image(args) -> bool:
  """Checks for correct docker image arguments.

  Args:
    args: user provided arguments for running the command.

  Returns:
    True if intended to use base docker image, False to use docker image.
  """
  use_base_docker_image = True
  # Check if (base_docker_image and script_dir) or (docker_image) is set.
  if args.docker_image is not None:
    if args.script_dir is not default_script_dir:
      xpk_print(
          '`--script-dir` and --docker-image can not be used together. Please'
          ' see `--help` command for more details.'
      )
      xpk_exit(1)
    if args.base_docker_image is not default_docker_image:
      xpk_print(
          '`--base-docker-image` and --docker-image can not be used together.'
          ' Please see `--help` command for more details.'
      )
      xpk_exit(1)
    use_base_docker_image = False
  return use_base_docker_image


def setup_docker_image(args) -> tuple[int, str]:
  """Does steps to verify docker args, check image, and build image (if asked).

  Args:
    args: user provided arguments for running the command.

  Returns:
    tuple:
      0 if successful and 1 otherwise.
      Name of the docker image to use.
  """
  use_base_docker_image = use_base_docker_image_or_docker_image(args)

  docker_image = args.base_docker_image
  if use_base_docker_image:
    validate_docker_image_code = validate_docker_image(docker_image, args)
    if validate_docker_image_code != 0:
      xpk_exit(validate_docker_image_code)
    build_docker_image_code, docker_image = build_docker_image_from_base_image(
        args
    )
    if build_docker_image_code != 0:
      xpk_exit(build_docker_image_code)
  else:
    docker_image = args.docker_image
    validate_docker_image_code = validate_docker_image(args.docker_image, args)
    if validate_docker_image_code != 0:
      xpk_exit(validate_docker_image_code)

  return 0, docker_image


def get_main_and_sidecar_container(args, system, docker_image) -> str:
  """Generate yaml for main and sidecar container.
  Args:
    args: user provided arguments for running the command.
    system: system characteristics
    docker_image: docker image

  Returns:
    str:
      yaml for main and sidecar container
  """
  resource_type = AcceleratorTypeToAcceleratorCharacteristics[
      system.accelerator_type
  ].resource_type
  main_container = get_main_container(args, system, docker_image, resource_type)
  yaml = """- name: stacktrace-explorer
                image: busybox:1.28
                args: [/bin/sh, -c, "check_signal() (while [ ! -f /shared-volume/stacktrace_signal ]; do sleep 1; done; pid=$(pidof 'tail'); kill $pid;); check_signal & while [ ! -d /tmp/debugging ]; do sleep 60; done; while [ ! -e /tmp/debugging/* ]; do sleep 60; done; tail -n+1 -f /tmp/debugging/*; exit 0;"]
                volumeMounts:
                - name: tpu-stack-trace
                  readOnly: true
                  mountPath: /tmp/debugging
                - name: shared-data
                  mountPath: /shared-volume
              {main_container}
  """
  return yaml.format(main_container=main_container)


def get_main_container(args, system, docker_image, resource_type) -> str:
  """Generate yaml for main container including the xpk command.
  Args:
    args: user provided arguments for running the command.
    system: system characteristics
    docker_image: docker image
    resource_type: The label to describe the resource type for TPUs/GPUs/CPUs.

  Returns:
    str:
      yaml for main container
  """

  xpk_internal_commands = ''
  gsutil_test_command = ''
  if not args.use_pathways and args.debug_dump_gcs:
    gsutil_test_command = (
        'which gsutil >/dev/null 2>&1 || { echo >&2 "gsutil'
        ' is required but not installed. Aborting"; exit 24;};'
    )
    xpk_internal_commands += (
        'WORKER_ID=$HOSTNAME;'
        f'gsutil -m cp -r /tmp/xla_dump/ {args.debug_dump_gcs}/$WORKER_ID;'
    )

  command = args.command
  if args.enable_debug_logs:
    command = (
        'TPU_STDERR_LOG_LEVEL=0 TPU_MIN_LOG_LEVEL=0 TF_CPP_MIN_LOG_LEVEL=0'
        f' TPU_VMODULE=real_program_continuator=1 {args.command}'
    )

  gpu_workload_terminate_command = ''
  if system.accelerator_type == AcceleratorType['GPU']:
    command = 'cd /deps && bash gpu_multi_process_run.sh'
    gpu_workload_terminate_command = (
        'echo Main app is done > /usr/share/workload/workload_terminated; '
    )

  tpu_stacktrace_terminate_command = ''
  if (
      not args.use_pathways
      and system.accelerator_type == AcceleratorType['TPU']
      and args.deploy_stacktrace_sidecar
  ):
    tpu_stacktrace_terminate_command = (
        'touch /shared-volume/stacktrace_signal; '
    )

  xpk_return_user_exit_code = ''
  if args.restart_on_user_code_failure:
    if int(args.max_restarts) <= 0:
      xpk_print(
          f'Warning: --max-restarts, is set to {args.max_restarts}. Will not'
          ' restart on user failure.'
      )
    xpk_return_user_exit_code = 'exit $EXIT_CODE'

  yaml = """- name: {docker_name}
                image: {docker_image}
                {image_pull_policy}
                env: {env}
                ports:
                {container_ports}
                {jax_coordinator_port}
                securityContext:
                  privileged: true
                command:
                - bash
                - -c
                - |
                  echo XPK Start: $(date);
                  _sigterm() (kill -SIGTERM $! 2>/dev/null;);
                  trap _sigterm SIGTERM;
                  {gsutil_test_command}
                  ({command}) & PID=$!;
                  while kill -0 $PID 2>/dev/null;
                      do sleep 5;
                  done;
                  wait $PID;
                  EXIT_CODE=$?;
                  {xpk_internal_commands}
                  echo XPK End: $(date);
                  echo EXIT_CODE=$EXIT_CODE;
                  {tpu_stacktrace_terminate_command}
                  {gpu_workload_terminate_command}
                  if [ "$EXIT_CODE" = 143 ]; then
                    exit $EXIT_CODE
                  fi
                  {xpk_return_user_exit_code}
                resources:
                  limits:
                    {resources}
                volumeMounts:
                {volume_mounts}
  """
  return yaml.format(
      args=args,
      system=system,
      image_pull_policy=add_image_pull_policy_for_pw_or_gpu(args, system),
      env=get_env_container(args, system),
      container_ports=add_container_ports(args, system),
      jax_coordinator_port=add_jax_coordinator_port(system),
      docker_name=get_main_container_docker_image(args, system),
      docker_image=docker_image,
      gsutil_test_command=gsutil_test_command,
      command=command,
      tpu_stacktrace_terminate_command=tpu_stacktrace_terminate_command,
      gpu_workload_terminate_command=gpu_workload_terminate_command,
      xpk_internal_commands=xpk_internal_commands,
      resources=get_main_container_resources(args, system, resource_type),
      volume_mounts=get_volume_mounts(args, system),
      xpk_return_user_exit_code=xpk_return_user_exit_code,
  )


def add_image_pull_policy_for_pw_or_gpu(args, system: SystemCharacteristics):
  """Add image pull policy only for Pathways containers.
  Args:
    args: user provided args.
    system: system characteristics

  Returns:
    str:
      YAML stating that the image will be pulled fro GCR every time.
  """
  yaml = """imagePullPolicy: Always"""

  if args.use_pathways or system.accelerator_type == AcceleratorType['GPU']:
    return yaml.format(args=args)
  return ''


def get_main_container_docker_image(args, system: SystemCharacteristics) -> str:
  """Docker name for the main container.
  Args:
    args: user provided args.
    system: system characteristics.

  Returns:
    str:
      Workload docker image as a YAML string
  """

  if system.accelerator_type == AcceleratorType['GPU']:
    return 'gpu-image'

  return f'{args.docker_name}'


def get_volumes(args, system: SystemCharacteristics) -> str:
  """Get volumes accessible to the containers in the pod.
  Args:
    args: user provided args.
    system: system characteristics.

  Returns:
    str:
      YAML for the volumes.
  """
  volumes = """- emptyDir:
                  medium: Memory
                name: dshm-2"""

  if (
      system.accelerator_type == AcceleratorType['TPU']
      and args.deploy_stacktrace_sidecar
  ):
    volumes += """
              - name: tpu-stack-trace
              - name: shared-data"""

  return volumes


def get_volume_mounts(args, system: SystemCharacteristics) -> str:
  """Resources for the main container.
  Args:
    args: user provided args.

  Returns:
    str:
      YAML for the volumes mounted within a Pathways container or GPU container as a YAML string.
  """
  volume_mount_yaml = """- mountPath: /dev/shm
                  name: dshm-2"""

  if args.use_pathways:
    volume_mount_yaml = """- mountPath: /tmp
                  name: shared-tmp"""
  elif (
      system.accelerator_type == AcceleratorType['TPU']
      and args.deploy_stacktrace_sidecar
  ):
    volume_mount_yaml += """
                - name: tpu-stack-trace
                  mountPath: /tmp/debugging
                - name: shared-data
                  mountPath: /shared-volume"""
  elif system.accelerator_type == AcceleratorType['GPU']:
    if system.device_type == h100_device_type:
      volume_mount_yaml = """- name: nvidia-install-dir-host
                  mountPath: /usr/local/nvidia/lib64
                - name: tcpx-nccl-plugin-volume
                  mountPath: /usr/local/tcpx
                - name: tcpd-socket
                  mountPath: /tmp
                - name: shared-memory
                  mountPath: /dev/shm
                - name: workload-terminated-volume
                  mountPath: /usr/share/workload"""
    elif system.device_type == h100_mega_device_type:
      volume_mount_yaml = """- name: nvidia-install-dir-host
                  mountPath: /usr/local/nvidia/lib64
                - name: shared-memory
                  mountPath: /dev/shm
                - name: workload-terminated-volume
                  mountPath: /usr/share/workload"""

  return volume_mount_yaml


def get_user_workload_container(args, system: SystemCharacteristics):
  """Deploy user workload container

  Args:
      args: user provided args.
      system: system characteristics.

  Returns:
      container: main container
      debugging_dashboard_id: id of the GKE dashboard
  """

  setup_docker_image_code, docker_image = setup_docker_image(args)
  if setup_docker_image_code != 0:
    xpk_exit(setup_docker_image_code)

  # Determine if we deploy a sidecar and if we deploy a container.
  debugging_dashboard_id = None
  resource_type = AcceleratorTypeToAcceleratorCharacteristics[
      system.accelerator_type
  ].resource_type
  if (
      not args.use_pathways
      and system.accelerator_type == AcceleratorType['TPU']
      and args.deploy_stacktrace_sidecar
  ):
    xpk_print(
        'Sidecar container to display stack traces for TPU workloads will also'
        ' be deployed.'
    )
    container = get_main_and_sidecar_container(args, system, docker_image)
    # Get GKE debugging dashboard only when sidecar container is deployed for TPU workloads
    debugging_dashboard_id = get_gke_debugging_dashboard(args)
  else:
    container = get_main_container(args, system, docker_image, resource_type)
  return container, debugging_dashboard_id


def get_env_container(args, system: SystemCharacteristics):
  """Environment configuration for the main container.
  Args:
    args: user provided args.
    system: system characteristics.

  Returns:
    str:
      YAML with the env config for the main container, as a YAML string.
  """
  pw_env_yaml = """
                - name: XCLOUD_ENVIRONMENT
                  value: GCP
                - name: JAX_PLATFORMS
                  value: proxy
                - name: JAX_BACKEND_TARGET
                  value: {proxy_address}
                - name: JOBSET_NAME
                  valueFrom:
                    fieldRef:
                      fieldPath: metadata.annotations['jobset.sigs.k8s.io/jobset-name']"""
  if args.use_pathways:
    return pw_env_yaml.format(
        args=args, proxy_address=args.pathways_proxy_address
    )

  gpu_env_yaml = """
                  - name: REPLICATED_JOB_NAME
                    valueFrom:
                      fieldRef:
                        fieldPath: metadata.annotations['jobset.sigs.k8s.io/replicatedjob-name']
                  - name: JOBSET_NAME
                    valueFrom:
                      fieldRef:
                        fieldPath: metadata.annotations['jobset.sigs.k8s.io/jobset-name']
                  - name: JAX_COORDINATOR_ADDRESS
                    value: "$(JOBSET_NAME)-$(REPLICATED_JOB_NAME)-0-0.$(JOBSET_NAME)"
                  - name: NNODES
                    value: "{args.num_nodes}"
                  - name: NODE_RANK
                    valueFrom:
                      fieldRef:
                        fieldPath: metadata.annotations['batch.kubernetes.io/job-completion-index']
                  - name: USE_GPUDIRECT
                    value: {gpu_direct_name}
                  - name: GPUS_PER_NODE
                    value: "{system.chips_per_vm}"
                  - name: JAX_COORDINATOR_PORT
                    value: "6002"
                  - name: LD_LIBRARY_PATH
                    value: /usr/local/nvidia/lib64
                  - name: COMMAND
                    value: "{args.command}"
                  {args.env}"""
  if system.accelerator_type == AcceleratorType['GPU']:
    gpu_direct_name = (
        'tcpx' if args.device_type == h100_device_type else 'fastrak'
    )
    return gpu_env_yaml.format(
        args=args, system=system, gpu_direct_name=gpu_direct_name
    )

  if system.accelerator_type == AcceleratorType['CPU']:
    return get_cpu_env(args.num_slices, args.env, system)

  return args.env


def get_main_container_resources(
    args, system: SystemCharacteristics, resource_type
) -> str:
  """Resources for the main container.
  Args:
    args: user provided args.
    system: system characteristics.
    resource_type: TPU / GPU / CPU

  Returns:
    str:
      Workload resources port as a YAML string
  """
  # Resources requirements for Pathways workload containers are known.
  resources_yaml = """cpu: "24"
                    memory: 100G"""
  if args.use_pathways:
    return resources_yaml

  gpu_resources_yaml = """nvidia.com/gpu: {system.chips_per_vm}"""
  if system.accelerator_type == AcceleratorType['GPU']:
    return gpu_resources_yaml.format(system=system)

  return f'{resource_type}: {system.chips_per_vm}'


def add_container_ports(args, system: SystemCharacteristics) -> str:
  """Add slice builder and megascale container ports,
  for non-pathways workloads.

  Args:
    args: user provided args.

  Returns:
    str:
      Pathways server port as a YAML string
  """
  port_yaml = """- containerPort: 8471
                - containerPort: 8080"""
  if args.use_pathways:
    return ''

  gpu_port_yaml = """- containerPort: 6002"""
  if system.accelerator_type == AcceleratorType['GPU']:
    return gpu_port_yaml
  return port_yaml


def add_jax_coordinator_port(system) -> str:
  """Add jax coordinator port only for CPUs

  Args:
    system: system characteristics.

  Returns:
    str:
      jax coordinator port as a YAML string
  """
  if system.accelerator_type == AcceleratorType['CPU']:
    return '- containerPort: 1234'
  return ''


def get_gke_dashboard(args, dashboard_filter):
  """Get the identifier of GKE dashboard deployed in the project.

  Args:
    args: user provided arguments for running the command.

  Returns:
    bool:
      True if 'gcloud monitoring dashboards list' returned an error or
      multiple dashboards with same filter exist in the project,
      False otherwise.
    str:
      identifier of dashboard if deployed in project,
      None otherwise.
  """
  command = (
      'gcloud monitoring dashboards list'
      f' --project={args.project} --filter="{dashboard_filter}"'
      ' --format="value(name)" --verbosity=error'
  )

  return_code, return_value = run_command_for_value(
      command, 'GKE Dashboard List', args
  )

  if return_code != 0:
    xpk_print(
        f'GKE Dashboard List request returned ERROR {return_code}. If there is'
        ' a permissions error, please check'
        ' https://github.com/google/xpk/blob/main/README.md#roles-needed-based-on-permission-errors'
        ' for possible solutions.'
    )
    return True, None

  if not return_value:
    xpk_print(
        f'No dashboard with {dashboard_filter} found in the'
        f' project:{args.project}.'
    )
    return False, return_value

  dashboards = return_value.strip().split('\n')
  if len(dashboards) > 1:
    xpk_print(
        f'Multiple dashboards with same {dashboard_filter} exist in the'
        f' project:{args.project}. Delete all but one dashboard deployed using'
        ' https://github.com/google/cloud-tpu-monitoring-debugging.'
    )
    return True, None

  if dashboards[0]:
    return False, dashboards[0].strip().split('/')[-1]

  return True, None


def get_gke_outlier_dashboard(args):
  """Get the identifier of GKE outlier dashboard deployed in the project.

  Args:
    args: user provided arguments for running the command.

  Returns:
    str:
      identifier of outlier dashboard if deployed in project,
      None otherwise.
  """
  outlier_dashboard_filter = "displayName:'GKE - TPU Monitoring Dashboard'"
  is_error, dashboard_id = get_gke_dashboard(args, outlier_dashboard_filter)

  # 'gcloud monitoring dashboards list' returned an error or multiple dashboards with same filter exist in the project
  if is_error:
    return None

  # 'gcloud monitoring dashboards list' succeeded but no dashboard for the filter exist in the project
  if not is_error and not dashboard_id:
    xpk_print(
        'Follow https://github.com/google/cloud-tpu-monitoring-debugging to'
        ' deploy monitoring dashboard to view statistics and outlier mode of'
        ' GKE metrics.'
    )
    return None

  return dashboard_id


def get_gke_debugging_dashboard(args):
  """Get the identifier of GKE debugging dashboard deployed in the project.

  Args:
    args: user provided arguments for running the command.

  Returns:
    str:
      identifier of debugging dashboard if deployed in project,
      None otherwise.
  """
  debugging_dashboard_filter = "displayName:'GKE - TPU Logging Dashboard'"
  is_error, dashboard_id = get_gke_dashboard(args, debugging_dashboard_filter)

  # 'gcloud monitoring dashboards list' returned an error or multiple dashboards with same filter exist in the project
  if is_error:
    return None

  # 'gcloud monitoring dashboards list' succeeded but no dashboard for the filter exist in the project
  if not is_error and not dashboard_id:
    xpk_print(
        'Follow https://github.com/google/cloud-tpu-monitoring-debugging to'
        ' deploy debugging dashboard to view stack traces collected in Cloud'
        ' Logging.'
    )
    return None

  return dashboard_id


def create_accelerator_label(accelerator_type, system) -> str:
  """Generates accelerator label.

  Args:
    accelerator_type: type of accelerator.
    system: system characteristics.

  Returns:
    The accelerator label.
  """
  if accelerator_type == AcceleratorType['CPU']:
    return ''
  return (
      f'{AcceleratorTypeToAcceleratorCharacteristics[accelerator_type].accelerator_label}:'
      f' {system.gke_accelerator}'
  )


def create_machine_label(
    accelerator_type, system, autoprovisioning_enabled: bool = False
) -> str:
  """Generates machine label.

  Args:
    accelerator_type: type of accelerator.
    system: system characteristics.
    autoprovisioning_enabled: describes autoprovisioning enablement.

  Returns:
    The machine label.
  """
  if (
      accelerator_type == AcceleratorType['TPU']
      and not autoprovisioning_enabled
  ):
    return (
        f'{AcceleratorTypeToAcceleratorCharacteristics[accelerator_type].machine_label}:'
        f' {system.topology}'
    )
  return ''


def calculate_process_count(num_slices, vms_per_slice) -> str:
  """Calculates the total number of processes in the workload.
  Args:
    num_slices: Number of slices to be used in the workload.
    vms_per_slice: number of VMs in each slice.

  Returns:
    str: total number of processes.
  """
  num_processes = int(num_slices) * int(vms_per_slice)

  return f'{num_processes}'


def get_cpu_env(num_slices, env_vars, system) -> str:
  """Generate environment variables for CPU nodepools
  Args:
    num_slices: Number of slices to be used in the workload.
    env_vars: Environment variables, processed from user args.
    system: system characteristics

  Returns:
    str: yaml containing env variables
  """
  yaml = """
                - name: REPLICATED_JOB_NAME
                  valueFrom:
                    fieldRef:
                      fieldPath: metadata.annotations['jobset.sigs.k8s.io/replicatedjob-name']
                - name: JOB_INDEX
                  valueFrom:
                    fieldRef:
                      fieldPath: metadata.annotations['jobset.sigs.k8s.io/job-index']
                - name: JOB_COMPLETION_INDEX
                  valueFrom:
                    fieldRef:
                      fieldPath: metadata.annotations['batch.kubernetes.io/job-completion-index']
                - name: PROCESSES_IN_JOB
                  value: "{processes_in_job}"
                - name: JAX_PROCESS_COUNT
                  value: "{process_count}"
                {env_vars}
                - name: JAX_COORDINATOR_ADDRESS
                  value: "$(JOBSET_NAME)-$(REPLICATED_JOB_NAME)-0-0.$(JOBSET_NAME)"
  """
  return yaml.format(
      processes_in_job=system.vms_per_slice,
      process_count=calculate_process_count(num_slices, system.vms_per_slice),
      env_vars=env_vars,
  )


def get_cpu_affinity(accelerator_type) -> str:
  """Generate affinity rules for CPU nodepools, so that workload pods are
  not scheduled on the default pool machines.
  Args:
    accelerator_type: TPU / GPU / CPU

  Returns:
    str: yaml containing affinity constraints
  """
  yaml = """affinity:
                nodeAffinity:
                  requiredDuringSchedulingIgnoredDuringExecution:
                    nodeSelectorTerms:
                    - matchExpressions:
                      - key: cloud.google.com/gke-nodepool
                        operator: NotIn
                        values:
                        - default-pool
"""
  if accelerator_type == AcceleratorType['CPU']:
    return yaml
  return ''


def get_gpu_scheduler(
    args, system: SystemCharacteristics, autoprovisioning_args: str
) -> tuple[str, int]:
  """Get gpu scheduler configuration.

  Args:
    args: user provided arguments for running the command.
    system: system characteristics.
    autoprovisioning_args: a string of arguments for Autoprovisioning.

  Returns:
    str: yaml containing gpu scheduler configuration
    int of 0 if successful and 1 otherwise.
  """
  gpu_scheduler = ''
  return_code = 0

  if args.scheduler == 'gke.io/topology-aware-auto':
    gpu_scheduler = f"""schedulingGates:
              - name: "{args.scheduler}-{args.workload}"
              """
  elif args.scheduler == 'default-scheduler':
    gpu_scheduler_yaml = """schedulerName: {scheduler_name}
              affinity:
                nodeAffinity:
                  requiredDuringSchedulingIgnoredDuringExecution:
                    nodeSelectorTerms:
                    - matchExpressions:
                      - key: cloud.google.com/gke-accelerator
                        operator: Exists
                      - key: cloud.google.com/gke-nodepool
                        operator: In
                        values: [{node_pool_name}]
              nodeSelector:
                {accelerator_label}
                {machine_label}
                {autoprovisioning_args}
              """
    gpu_scheduler = gpu_scheduler_yaml.format(
        scheduler_name=args.scheduler,
        accelerator_label=create_accelerator_label(
            system.accelerator_type, system
        ),
        machine_label=create_machine_label(system.accelerator_type, system),
        node_pool_name=f'{args.cluster}-np-0',
        autoprovisioning_args=autoprovisioning_args,
    )
  else:
    return_code = 1
    xpk_print(
        '--scheduler needs to be set as either `default-scheduler`'
        ' or `gke.io/topology-aware-auto` in order to schedule the'
        ' workloads on GPUs.'
    )

  return gpu_scheduler, return_code


def get_gpu_volume(system: SystemCharacteristics) -> str:
  """Get gpu volume based on user provided arguments.

  Args:
    system: system characteristics.

  Returns:
    str: yaml containing gpu volume
  """
  gpu_volume = ''
  if system.device_type == h100_device_type:
    gpu_volume = """- name: nvidia-install-dir-host
                hostPath:
                  path: /home/kubernetes/bin/nvidia/lib64
              - name: tcpd-socket
                hostPath:
                  path: /run/tcpx
              - name: shared-memory
                emptyDir:
                  medium: "Memory"
                  sizeLimit: 200Gi
              - name: workload-terminated-volume
                emptyDir:
              - name: tcpx-nccl-plugin-volume
                emptyDir:"""
  elif system.device_type == h100_mega_device_type:
    gpu_volume = """- name: nvidia-install-dir-host
                hostPath:
                  path: /home/kubernetes/bin/nvidia/lib64
              - name: shared-memory
                emptyDir:
                  medium: "Memory"
                  sizeLimit: 1Gi
              - name: workload-terminated-volume
                emptyDir:"""
  return gpu_volume


def get_gpu_rxdm_image(system: SystemCharacteristics) -> str:
  """Get config of rxdm based on user provided arguments.

  Args:
    system: system characteristics.

  Returns:
    str: yaml containing the rxdm name and image
  """
  gpu_rxdm_image = ''
  if system.device_type == h100_device_type:
    gpu_rxdm_image = """- name: tcpd-daemon
                image: us-docker.pkg.dev/gce-ai-infra/gpudirect-tcpx/tcpgpudmarxd-dev:v2.0.9"""
  elif system.device_type == h100_mega_device_type:
    gpu_rxdm_image = """- name: fastrak-daemon
                image: us-docker.pkg.dev/gce-ai-infra/gpudirect-tcpxo/tcpgpudmarxd-dev:v1.0.9"""
  return gpu_rxdm_image


def get_gpu_rxdm_cmd(system: SystemCharacteristics) -> str:
  """Get rxdm command based on user provided arguments.

  Args:
    system: system characteristics.

  Returns:
    str: command of running rxdm container
  """
  gpu_rxdm_cmd = ''
  if system.device_type == h100_device_type:
    gpu_rxdm_cmd = (
        '/tcpgpudmarxd/build/app/tcpgpudmarxd --gpu_nic_preset a3vm'
        ' --gpu_shmem_type fd --setup_param "--verbose 128 2 0"'
    )
  elif system.device_type == h100_mega_device_type:
    gpu_rxdm_cmd = (
        'set -ex; chmod 755 /fts/entrypoint_rxdm_container.sh;'
        ' /fts/entrypoint_rxdm_container.sh --num_hops=2 --num_nics=8 --uid='
        ' --alsologtostderr'
    )
  return gpu_rxdm_cmd


def get_gpu_tcp_volume(system: SystemCharacteristics) -> str:
  """Get gpu tcp volume based on user provided arguments.

  Args:
    system: system characteristics.

  Returns:
    str: yaml containing gpu tcp volume
  """
  gpu_tcp_volume = ''
  if system.device_type == h100_device_type:
    gpu_tcp_volume = """- name: tcpd-socket
                  mountPath: /tmp"""
  return gpu_tcp_volume


def wait_for_job_completion(args) -> int:
  """Function to wait for job completion.

  Args:
    args: user provided arguments for running the command.

  Returns:
    return_code: 0 if successful, 124 if timeout, 125 if unsuccessful job, 1 otherwise
  """
  # Check that the workload exists
  args.workload = args.wait_for_job_completion
  workload_exists = check_if_workload_exists(args)
  if not workload_exists:
    xpk_print(f'Workload named {args.workload} does not exist.')
    return 1

  # Get the full workload name
  get_workload_name_cmd = f'kubectl get workloads | grep jobset-{args.workload}'
  return_code, return_value = run_command_for_value(
      get_workload_name_cmd, 'Get full workload name', args
  )
  if return_code != 0:
    xpk_print(f'Get full workload name request returned ERROR {return_code}')
    return return_code
  full_workload_name = return_value.split(' ')[0]

  # Call kubectl wait on the workload using the full workload name
  timeout_val = args.timeout if args.timeout is not None else -1
  timeout_msg = (
      f'{timeout_val}s' if timeout_val != -1 else 'max timeout (1 week)'
  )
  wait_cmd = (
      "kubectl  wait --for jsonpath='.status.conditions[-1].type'=Finished"
      f' workload {full_workload_name} --timeout={timeout_val}s'
  )
  return_code, return_value = run_command_for_value(
      wait_cmd,
      f'Wait for workload to finish with timeout of {timeout_msg}',
      args,
      print_timer=True,
  )
  if return_code != 0:
    if 'timed out' in return_value:
      xpk_print(
          f'Timed out waiting for your workload after {timeout_msg}, see your'
          ' workload here:'
          # pylint: disable=line-too-long
          f' https://console.cloud.google.com/kubernetes/service/{zone_to_region(args.zone)}/{args.cluster}/default/{args.workload}/details?project={args.project}'
      )
      return 124
    else:
      xpk_print(f'{return_value}')
      xpk_print(f'Wait for workload returned ERROR {return_code}')
      return return_code
  xpk_print(
      'Finished waiting for your workload, see your workload here:'
      # pylint: disable=line-too-long
      f' https://console.cloud.google.com/kubernetes/service/{zone_to_region(args.zone)}/{args.cluster}/default/{args.workload}/details?project={args.project}'
  )
  status_cmd = (
      f'kubectl get jobset {args.workload} -o'
      " jsonpath='{.status.conditions[-1].type}'"
  )
  return_code, return_value = run_command_for_value(
      status_cmd, 'Get jobset status', args
  )
  if return_code != 0:
    xpk_print(f'Get workload status request returned ERROR {return_code}')
    return return_code
  xpk_print(f'Your workload finished with status: {return_value}')
  if return_value != 'Completed':
    xpk_print('Your workload did not complete successfully')
    return 125
  return 0
