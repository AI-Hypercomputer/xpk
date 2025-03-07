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

from dataclasses import dataclass

from ..utils.console import xpk_print
from ..utils.file import write_tmp_file
from .capacity import (
    AUTOPROVISIONING_CONFIG_MAXIMUM_KEY,
    AUTOPROVISIONING_CONFIG_MINIMUM_KEY,
    AUTOPROVISIONING_CONFIG_VALUE,
    CAPACITY_TYPE_CONFIG_KEY,
    RESERVATION_CONFIG_KEY,
    CapacityType,
    get_capacity_type,
)
from .commands import run_command_for_value, run_commands
from .config import XPK_CURRENT_VERSION
from .system_characteristics import AcceleratorType, get_system_characteristics_by_device_type, SystemCharacteristics

CLUSTER_RESOURCES_CONFIGMAP = 'resources-configmap'
CLUSTER_METADATA_CONFIGMAP = 'metadata-configmap'

CLUSTER_CONFIGMAP_YAML = """kind: ConfigMap
apiVersion: v1
metadata:
  name: {name}
data:
  {data}
"""


@dataclass
class AutoprovisioningConfig:
  config_filename: str
  minimum_chips: int
  maximum_chips: int


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
  resources_yml = CLUSTER_CONFIGMAP_YAML.format(
      args=args, name=resources_configmap_name, data=resources_data
  )
  configmap_yml[resources_configmap_name] = resources_yml

  # ConfigMap to store cluster metadata.
  # XPK Version.
  metadata = f'xpk_version: {XPK_CURRENT_VERSION}'
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
  metadata_yml = CLUSTER_CONFIGMAP_YAML.format(
      args=args, name=metadata_configmap_name, data=metadata
  )
  configmap_yml[metadata_configmap_name] = metadata_yml
  return create_or_update_cluster_configmap(configmap_yml)


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


def get_cluster_system_characteristics(args) -> SystemCharacteristics | None:
  """Get systemCharcteristics based on the cluster resources configMap
  Args:
    args: user provided arguments for running the command.

  Returns:
    returns system characteristics
  """
  resources_configmap_name = f'{args.cluster}-{CLUSTER_RESOURCES_CONFIGMAP}'
  cluster_config_map = get_cluster_configmap(args, resources_configmap_name)

  if cluster_config_map is None:
    return None

  for key in cluster_config_map:
    system, result_code = get_system_characteristics_by_device_type(key)
    if result_code == 0:
      return system

  return None
