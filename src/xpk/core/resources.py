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
from .capacity import (
    AUTOPROVISIONING_CONFIG_MAXIMUM_KEY,
    AUTOPROVISIONING_CONFIG_MINIMUM_KEY,
    AUTOPROVISIONING_CONFIG_VALUE,
    CAPACITY_TYPE_CONFIG_KEY,
    RESERVATION_CONFIG_KEY,
    CapacityManager,
    CapacityType,
)
from .commands import run_command_for_value, run_commands
from .config import XPK_CURRENT_VERSION
from .system_characteristics import (
    AcceleratorType,
    SystemCharacteristics,
    get_system_characteristics_by_device_type,
)


class ResourceManager:
  """Handles cluster resource management, including ConfigMap operations."""

  CLUSTER_RESOURCES_CONFIGMAP = 'resources-configmap'
  CLUSTER_METADATA_CONFIGMAP = 'metadata-configmap'
  CLUSTER_CONFIGMAP_YAML = """kind: ConfigMap
apiVersion: v1
metadata:
  name: {name}
data:
  {data}
"""

  def __init__(self, args, capacity_manager: CapacityManager, system=None):
    self.args = args
    self.system = system
    self.resources_configmap_name = (
        f'{args.cluster}-{self.CLUSTER_RESOURCES_CONFIGMAP}'
    )
    self.metadata_configmap_name = (
        f'{args.cluster}-{self.CLUSTER_METADATA_CONFIGMAP}'
    )
    self.capacity_manager = capacity_manager

  def get_cluster_configmap(self, configmap_name) -> dict[str, str] | None:
    """Run the Get GKE Cluster ConfigMap request.

    Returns:
      key:value pairs stored in cluster ConfigMap.
    """
    command = (
        'kubectl get configmap'
        f' {configmap_name} -o=custom-columns="ConfigData:data"'
        ' --no-headers=true'
    )
    return_code, return_value = run_command_for_value(
        command, 'GKE Cluster Get ConfigMap', self.args
    )
    if return_code != 0:
      xpk_print(
          f'GKE Cluster Get ConfigMap request returned ERROR {return_code}'
      )
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

  def get_resources_configmap(self) -> dict[str, str] | None:
    """Gets the resources ConfigMap."""

    return self.get_cluster_configmap(self.resources_configmap_name)

  def get_metadata_configmap(self) -> dict[str, str] | None:
    """Gets the metadata ConfigMap."""

    return self.get_cluster_configmap(self.metadata_configmap_name)

  def get_resources_configmap_name(self) -> str:
    """Returns the resources ConfigMap name."""

    return self.resources_configmap_name

  def get_metadata_configmap_name(self) -> str:
    """Returns the metadata ConfigMap name."""

    return self.resources_configmap_name

  def create_configmap_string(self, resources_data: str) -> str:
    """Creates a ConfigMap YAML string using the CLUSTER_CONFIGMAP_YAML template."""

    return self.CLUSTER_CONFIGMAP_YAML.format(
        name=self.resources_configmap_name, data=resources_data
    )

  def create_cluster_configmaps(
      self,
      tensorboard_config: dict,
      autoprovisioning_config=None,
  ) -> int:
    """Run the Create GKE Cluster ConfigMap request.

    Args:
      tensorboard_config: map that contains Vertex Tensorboard name, id and location
      autoprovisioning_config: Config used in autoprovisioning.

    Returns:
      0 if successful and 1 otherwise.
    """
    configmap_yml = {}

    if self.system is None:
      xpk_print('System is None. Skipping configmap creation.')
      return 1

    # ConfigMap to store resources available in the cluster.
    if self.system.accelerator_type == AcceleratorType['GPU']:
      resources_data = (
          f'{self.system.device_type}: "{int(self.args.num_nodes)}"'
      )
    elif (
        not self.args.enable_pathways
        and self.args.enable_autoprovisioning
        and autoprovisioning_config
    ):
      # Currently autoprovisioning is not supported with Pathways.
      # Auto provisioning will have variable topologies for a gke accelerator type.
      resources_data = (
          f'{self.system.gke_accelerator}: {AUTOPROVISIONING_CONFIG_VALUE}\n '
          f' {AUTOPROVISIONING_CONFIG_MINIMUM_KEY}:'
          f' "{autoprovisioning_config.minimum_chips}"\n '
          f' {AUTOPROVISIONING_CONFIG_MAXIMUM_KEY}:'
          f' "{autoprovisioning_config.maximum_chips}"'
      )
    else:
      resources_data = (
          f'{self.system.device_type}:'
          f' "{int(self.args.num_slices) * self.system.vms_per_slice}"'
      )

    configmap_yml[self.resources_configmap_name] = (
        self.CLUSTER_CONFIGMAP_YAML.format(
            name=self.resources_configmap_name, data=resources_data
        )
    )

    # ConfigMap to store cluster metadata.
    # XPK Version.
    metadata = f'xpk_version: {XPK_CURRENT_VERSION}'
    # Vertex Tensorboard information
    for key, value in tensorboard_config.items():
      metadata += f'\n  {key}: "{value}"'
    # Capacity Type.
    capacity_type, return_code = self.capacity_manager.get_capacity_type()
    if return_code != 0:
      xpk_print('Unable to determine capacity type.')
      return return_code
    metadata += f'\n  {CAPACITY_TYPE_CONFIG_KEY}: {capacity_type.name}'
    # Reservation ID if applicable.
    if capacity_type == CapacityType.RESERVATION:
      metadata += f'\n  {RESERVATION_CONFIG_KEY}: {self.args.reservation}'

    configmap_yml[self.metadata_configmap_name] = (
        self.CLUSTER_CONFIGMAP_YAML.format(
            name=self.metadata_configmap_name, data=metadata
        )
    )

    return self.create_or_update_cluster_configmap(configmap_yml)

  def create_or_update_cluster_configmap(self, configmap_yml: dict) -> int:
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

  def check_cluster_resources(self) -> tuple[bool, bool]:
    """Check if cluster has resources of a specified device_type/gke_accelerator.
    This check will be skipped if <args.cluster>-<_CLUSTER_RESOURCES_CONFIGMAP> ConfigMap doesn't exist for the cluster.

    Returns:
      Tuple of bool, bool
      True if resources in the cluster should be checked, False otherwise.
      True if device_type/gke_accelerator exists in the cluster, False otherwise.
    """
    resources_configmap = self.get_resources_configmap()
    if resources_configmap is None:
      xpk_print(
          'No ConfigMap exist for cluster with the name'
          f' {resources_configmap}. Cluster resources check will be'
          ' skipped.'
      )
      return False, False

    if self.system and (
        self.system.device_type in resources_configmap
        or self.system.gke_accelerator in resources_configmap
    ):
      return True, True

    return True, False

  def get_cluster_system_characteristics(self) -> SystemCharacteristics | None:
    """Get systemCharcteristics based on the cluster resources configMap

    Returns:
      returns system characteristics
    """
    resources_configmap_name = (
        f'{self.args.cluster}-{self.CLUSTER_RESOURCES_CONFIGMAP}'
    )
    cluster_config_map = self.get_cluster_configmap(resources_configmap_name)

    if cluster_config_map is None:
      return None

    for key in cluster_config_map:
      system, result_code = get_system_characteristics_by_device_type(key)
      if result_code == 0:
        return system

    return None

  def get_total_chips_requested_from_args(self) -> int:
    """Return the total chips requested based on user args.

    Returns:
      num of chips for the current request.
    """
    if self.system is None:
      return 0

    if self.system.accelerator_type == AcceleratorType['GPU']:
      return int(
          self.system.vms_per_slice
          * self.system.chips_per_vm
          * self.args.num_nodes
      )

    return int(
        self.system.vms_per_slice
        * self.system.chips_per_vm
        * self.args.num_slices
    )
