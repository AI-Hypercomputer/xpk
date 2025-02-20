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
import importlib.metadata as importlib_metadata
from argparse import Namespace
from dataclasses import dataclass

from ..utils.file import write_tmp_file
from ..utils.console import get_user_input, xpk_exit, xpk_print
from google.api_core.exceptions import PermissionDenied
from google.cloud import resourcemanager_v3
from kubernetes import client as k8s_client
from kubernetes import config
from kubernetes.client.exceptions import ApiException

from .commands import (
    run_command_for_value,
    run_command_with_updates,
    run_command_with_updates_retry,
    run_commands,
)
from .storage import GCP_FILESTORE_TYPE, Storage, get_storages_to_mount, GCS_FUSE_TYPE
from .system_characteristics import (
    AcceleratorType,
    AcceleratorTypeToAcceleratorCharacteristics,
    SystemCharacteristics,
)

################### Internally used constants ##############

default_docker_image = 'python:3.10'
default_script_dir = os.getcwd()
# This is the version for XPK PyPI package
__version__ = importlib_metadata.version('xpk')

xpk_current_version = __version__.split('+')[0]

h100_device_type = 'h100-80gb-8'
h100_mega_device_type = 'h100-mega-80gb-8'
h200_device_type = 'h200-141gb-8'

JOBSET_VERSION = 'v0.7.2'

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
CLOUD_PLATFORM_AUTH_SCOPE_URL = (
    '"https://www.googleapis.com/auth/cloud-platform"'
)
PLATFORM = 'linux/amd64'
GCS_FUSE_ANNOTATION = 'gke-gcsfuse/volumes: "true"'


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
  xpk_print(f'Working on {args.project} and {args.zone}')


def parse_env_config(args, tensorboard_config, system: SystemCharacteristics):
  """Parses the environment configurations to the jobset config.

  Args:
    args: user provided arguments for running the command.
    tensorboard_config: configuration of Vertex Tensorboard.
    system: system characteristics.
  """
  env = {}

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


def project_id_to_project_number(project_id: str) -> str:
  client = resourcemanager_v3.ProjectsClient()
  request = resourcemanager_v3.GetProjectRequest()
  request.name = f'projects/{project_id}'
  try:
    response: resourcemanager_v3.Project = client.get_project(request=request)
  except PermissionDenied as e:
    xpk_print(
        f"Couldn't translate project id: {project_id} to project number."
        f' Error: {e}'
    )
    xpk_exit(1)
  parts = response.name.split('/', 1)
  xpk_print(f'Project number for project: {project_id} is {parts[1]}')
  return parts[1]


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


def setup_k8s_env(args: Namespace) -> k8s_client.ApiClient:
  add_zone_and_project(args)
  get_cluster_credentials(args)
  args.project_number = project_id_to_project_number(args.project)

  config.load_kube_config()
  return k8s_client.ApiClient()


def create_k8s_service_account(name: str, namespace: str) -> None:
  k8s_core_client = k8s_client.CoreV1Api()
  sa = k8s_client.V1ServiceAccount(metadata=k8s_client.V1ObjectMeta(name=name))

  xpk_print(f'Creating a new service account: {name}')
  try:
    k8s_core_client.create_namespaced_service_account(
        namespace, sa, pretty=True
    )
    xpk_print(f'Created a new service account: {sa} successfully')
  except ApiException:
    xpk_print(f'Service account: {name} already exists. Skipping its creation')


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
    if (
        args.enable_workload_identity
        or args.enable_gcsfuse_csi_driver
        or args.enable_gcpfilestore_csi_driver
    ):
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
          f' --scopes=storage-full,gke-default,{CLOUD_PLATFORM_AUTH_SCOPE_URL}'
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
          f' --scopes={CLOUD_PLATFORM_AUTH_SCOPE_URL} --additional-node-network'
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
      command += (
          f' --scopes=storage-full,gke-default,{CLOUD_PLATFORM_AUTH_SCOPE_URL}'
      )

    if (
        args.enable_workload_identity
        or args.enable_gcsfuse_csi_driver
        or args.enable_gcpfilestore_csi_driver
    ):
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
          f' {node_pool_name} --node-version={gke_node_pool_version} --cluster={args.cluster} --project={args.project} --node-locations={args.zone} --region={zone_to_region(args.zone)} --num-nodes=1'
          f' --machine-type={args.pathways_gce_machine_type} --scopes=storage-full,gke-default,{CLOUD_PLATFORM_AUTH_SCOPE_URL} --enable-autoscaling'
          ' --min-nodes=1 --max-nodes=20'
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
      f' https://github.com/kubernetes-sigs/jobset/releases/download/{JOBSET_VERSION}/manifests.yaml'
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
  base_command_description = 'Determine server supported GKE versions for '

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
    master_gke_version = current_gke_master_version.strip()
    node_pool_gke_version = ''
    # Select minimum version which is >= master_gke_version and has the same minor version.
    # If this does not exist select maximum version which is < master_gke_version.
    for version in gke_server_config.valid_versions:
      if (
          (node_pool_gke_version == '' or node_pool_gke_version < version)
          and version < master_gke_version
      ) or (
          (node_pool_gke_version == '' or node_pool_gke_version > version)
          and master_gke_version <= version
          and master_gke_version.split('.')[:2] == version.split('.')[:2]
      ):
        node_pool_gke_version = version

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


def get_cluster_credentials(args: Namespace) -> None:
  """Run cluster configuration command to set the kubectl config.

  Args:
    args: user provided arguments for running the command.

  Returns:
    0 if successful and 1 otherwise.
  """
  command = (
      'gcloud container clusters get-credentials'
      f' {args.cluster} --region={zone_to_region(args.zone)}'
      f' --project={args.project} &&'
      ' kubectl config view && kubectl config set-context --current'
      ' --namespace=default'
  )
  task = f'get-credentials to cluster {args.cluster}'
  return_code = run_command_with_updates_retry(
      command, task, args, verbose=False
  )
  if return_code != 0:
    xpk_print(f'{task} returned ERROR {return_code}')
    xpk_exit(return_code)


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
      f'docker buildx build --platform={PLATFORM} -f {str(tmp.file.name)} -t'
      f' {docker_name} {args.script_dir}'
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
  if not cluster_config_map.get(system.gke_accelerator):
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
        'export TPU_STDERR_LOG_LEVEL=0 &&'
        ' export TPU_MIN_LOG_LEVEL=0 &&'
        ' export TF_CPP_MIN_LOG_LEVEL=0 &&'
        ' export TPU_VMODULE=real_program_continuator=1 &&'
        f' {args.command}'
    )

  gpu_workload_terminate_command = ''
  if system.accelerator_type == AcceleratorType['GPU']:
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
                  exit $EXIT_CODE
                resources:
                  limits:
                    {resources}
"""
  volume_mounts = get_volume_mounts(args, system)
  if volume_mounts != '':
    yaml += """
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
      volume_mounts=volume_mounts,
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









