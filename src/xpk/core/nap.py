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

from ..utils.console import xpk_print
from ..utils.file import write_tmp_file
from ..utils.objects import get_value_from_map
from .capacity import (
    AUTOPROVISIONING_CONFIG_VALUE,
    CAPACITY_TYPE_CONFIG_KEY,
    RESERVATION_CONFIG_KEY,
    CapacityType,
    get_capacity_node_selectors_from_capacity_type,
    get_capacity_type,
    verify_reservation_exists,
)
from .commands import run_command_with_updates, run_commands
from .gcloud_context import zone_to_region
from .nodepool import get_all_nodepools_programmatic
from .resources import (
    CLUSTER_METADATA_CONFIGMAP,
    CLUSTER_RESOURCES_CONFIGMAP,
    AutoprovisioningConfig,
    get_cluster_configmap,
)
from .scheduling import get_total_chips_requested_from_args
from .system_characteristics import AcceleratorType, SystemCharacteristics

AUTOPROVISIONING_CONFIG_FILE = """
management:
  autoRepair: true
  autoUpgrade: true
autoprovisioningLocations:
  {zones}
{resource_limits}
"""
AUTOPROVISIONING_RESOURCE_LIMITS = """
resourceLimits:
- resourceType: 'cpu'
  {cpu_limits}
- resourceType: 'memory'
  {memory_limits}
{custom_resource_type}
"""
AUTOPROVISIONING_CUSTOM_RESOURCE_TYPE = """
- resourceType: {resource_type}
  minimum: {minimum}
  maximum: {maximum}
"""


def enable_autoprovisioning_on_cluster(
    args, system: SystemCharacteristics | None
) -> tuple[AutoprovisioningConfig | None, int]:
  """Enable autoprovisioning on the cluster.

  Args:
    args: user provided arguments for running the command.
    system: system characteristics.

  Returns:
    Autoprovisioning Config or None.
    0 if successful and 1 otherwise.
  """
  if not system:
    return None, 1

  # TODO(@vbarr): Disable NAP if they call xpk cluster create again without --enable-autoprovisioning.
  # TODO(@vbarr): Support Pathways.
  # TODO(@vbarr): Support timeout period for idle np before they are deleted.
  # TODO(@vbarr): Support for hot idle configuration (timeout period is infinity).
  return_code = 0
  if system.accelerator_type == AcceleratorType['CPU']:
    xpk_print("Error: XPK NAP doesn't support Accelerators of Types: CPUs.")
    return None, 1

  autoprovisioning_config, return_code = create_autoprovisioning_config(
      args, system
  )
  if return_code != 0 or not autoprovisioning_config:
    xpk_print('Unable to create autoprovisioning config.')
    return autoprovisioning_config, return_code

  command = (
      'gcloud container clusters update'
      f' {args.cluster} --project={args.project}'
      f' --region={zone_to_region(args.zone)} --enable-autoprovisioning'
      ' --autoprovisioning-config-file'
      f' {autoprovisioning_config.config_filename}'
  )
  task = 'Update cluster with autoprovisioning enabled'
  return_code = run_command_with_updates(command, task, args)
  if return_code != 0:
    xpk_print(f'{task} request returned ERROR {return_code}')
    return autoprovisioning_config, return_code

  # Update created accelerator node pools to support autoprovisioning.
  existing_node_pool_names, return_code = get_all_nodepools_programmatic(args)
  if return_code != 0:
    xpk_print('Listing all node pools failed!')
    return autoprovisioning_config, return_code

  desired_node_pool_names = [
      f'{args.cluster}-np-{slice_num}' for slice_num in range(args.num_slices)
  ]

  commands = []
  task_names = []
  for node_pool_name in desired_node_pool_names:
    if node_pool_name not in existing_node_pool_names:
      # Ignore node pools that are not created yet, and not of the accelerator type.
      continue
    commands.append(
        f'gcloud container node-pools update {node_pool_name}'
        f' --cluster {args.cluster}'
        f' --project={args.project}'
        f' --region={zone_to_region(args.zone)}'
        ' --enable-autoprovisioning'
        ' --enable-autoscaling'
    )
    task_name = (
        f'Update node pool {node_pool_name} with autoprovisioning support.'
    )
    task_names.append(task_name)

  for i, command in enumerate(commands):
    xpk_print(f'To complete {task_names[i]} we are executing {command}')
  max_return_code = run_commands(
      commands,
      'Update node pools with autoprovisioning support',
      task_names,
      dry_run=args.dry_run,
  )
  if max_return_code != 0:
    xpk_print(
        'Update node pools with autoprovisioning support returned ERROR:'
        f' {max_return_code}'
    )
    return None, max_return_code
  return autoprovisioning_config, return_code


def create_autoprovisioning_config(
    args, system: SystemCharacteristics
) -> tuple[AutoprovisioningConfig | None, int]:
  """Create autoprovisioning config based on template file and user args

  Args:
    args: user provided arguments for running the command.
    system: system characteristics.

  Returns:
    tuple[AutoprovisioningConfig, int]
    AutoprovisioningConfig: config used to enable autoprovisioning
    int: return code
  """

  # CPU Limits and Memory Limits are for user jobs only. The default node pool
  # is not controlled by NAP.
  cpu_limits = """
  minimum: 1
  maximum: 10000
  """
  memory_limits = """
  minimum: 1
  maximum: 10000
  """

  # By default, the maximum chips is set to be the current number of resources used
  # in the cluster. The minimum is set to zero.
  minimum = 0
  maximum = get_total_chips_requested_from_args(args, system)
  xpk_print(f'Default Chips quota is minimum: {minimum}, maximum: {maximum}.')

  # Check for user overrides.
  if args.autoprovisioning_min_chips:
    minimum = args.autoprovisioning_min_chips
    xpk_print(
        f'User provided min chip quota of {minimum}. Overriding defaults.'
    )
  if args.autoprovisioning_max_chips:
    maximum = args.autoprovisioning_max_chips
    xpk_print(
        f'User provided max chip quota of {maximum}. Overriding defaults.'
    )

  # Check for edge cases in min and max chip values.
  if minimum < 0:
    xpk_print(
        f'Error: Minimum chips is set to {minimum}, and must be zero or'
        ' greater.'
    )
    return None, 1
  if maximum <= minimum or maximum < 0:
    xpk_print(
        f'Error: Maximum chips is set to {maximum}, and must be greater than'
        f' zero and greater or equal to minimum: {minimum}.Use'
        ' --autoprovisioning-max-chips=$MAX_CHIPS to adjust.'
    )
    return None, 1
  xpk_print(
      f'Chips quota is minimum: {minimum}, maximum: {maximum}. XPK will'
      f' autoprovision {maximum - minimum} chips based on incoming workload'
      f' requests, keeping at least {minimum} available at all times, and'
      f' maximum of {maximum}. If the difference ({maximum - minimum} chips) is'
      ' small, rescaling will not work well.'
  )

  custom_resource_string = AUTOPROVISIONING_CUSTOM_RESOURCE_TYPE.format(
      resource_type=system.gke_accelerator,
      minimum=minimum,
      maximum=maximum,
  )

  resource_limits = AUTOPROVISIONING_RESOURCE_LIMITS.format(
      cpu_limits=cpu_limits,
      memory_limits=memory_limits,
      custom_resource_type=custom_resource_string,
  )

  yml_string = AUTOPROVISIONING_CONFIG_FILE.format(
      resource_limits=resource_limits,
      zones=f'- {args.zone}',
  )
  autoprovisioning_config = AutoprovisioningConfig(
      config_filename=write_tmp_file(yml_string).name,
      minimum_chips=minimum,
      maximum_chips=maximum,
  )
  return autoprovisioning_config, 0


def is_autoprovisioning_enabled(
    args, system: SystemCharacteristics
) -> tuple[bool, int]:
  """Determine if autoprovisioning is enabled.

  Args:
    args: user provided arguments for running the command.
    system: system characteristics.

  Returns:
    bool is true if autoprovisioning is enabled, false otherwise.
    int of 0 if successful and 1 otherwise.
  """
  resources_configmap_name = f'{args.cluster}-{CLUSTER_RESOURCES_CONFIGMAP}'
  cluster_config_map = get_cluster_configmap(args, resources_configmap_name)

  if cluster_config_map is None:
    xpk_print(
        f'Unable to find config map: {resources_configmap_name}.'
        ' Autoprovisioning is not enabled.'
    )
    return False, 0

  return_code, autoprovisioning_value = get_value_from_map(
      system.gke_accelerator, cluster_config_map, verbose=False
  )
  if return_code != 0:
    xpk_print(
        'gke_accelerator type not found in config map:'
        f' {resources_configmap_name}. Autoprovisioning is not enabled.'
    )
    return False, 0

  if autoprovisioning_value == AUTOPROVISIONING_CONFIG_VALUE:
    xpk_print('Autoprovisioning is Enabled.')
    return True, 0
  else:
    xpk_print(
        'Error: Autoprovisioning not enabled but should be so exiting xpk.'
        f' Value should be {AUTOPROVISIONING_CONFIG_VALUE} but instead found'
        f' value of {autoprovisioning_value}'
    )
    return False, 1


def get_autoprovisioning_node_selector_args(args) -> tuple[str, int]:
  """Determine the capacity type when autoprovisioning is enabled.

  Args:
    args: user provided arguments for running the command.

  Returns:
    Tuple with string of autoprovisioning node selector args and
    int of 0 if successful and 1 otherwise.
  """
  return_code = 0
  node_selector_args = ''
  # If the user doesn't specify args, then use the cluster settings.
  capacity_type, return_code = get_capacity_type(args)
  capacity_type_str = capacity_type.name
  if return_code != 0:
    xpk_print('Unable to get capacity type.')
    return node_selector_args, return_code

  if capacity_type_str == CapacityType.UNKNOWN.name:
    # Use default settings from cluster creation.
    metadata_configmap_name = f'{args.cluster}-{CLUSTER_METADATA_CONFIGMAP}'
    cluster_config_map = get_cluster_configmap(args, metadata_configmap_name)

    # Error out if the metadata config map doesn't exist, and is attempting to use
    # autoprovisioning.
    if cluster_config_map is None:
      xpk_print(
          'Unable to find config map. Please specify a capacity type'
          ' --on-demand, --spot, --reservation=$RESERVATION_ID) to continue'
          ' to use autoprovisioning (--enable-autoprovisioning).'
      )
      return node_selector_args, 1

    return_code, capacity_type_str = get_value_from_map(
        CAPACITY_TYPE_CONFIG_KEY, cluster_config_map
    )
    if return_code != 0:
      return node_selector_args, return_code

    if capacity_type_str == CapacityType.RESERVATION.name:
      return_code, args.reservation = get_value_from_map(
          RESERVATION_CONFIG_KEY, cluster_config_map
      )
      if return_code != 0:
        return node_selector_args, return_code
      return_code = verify_reservation_exists(args)
      if return_code > 0:
        xpk_print('Unable to verify reservation name saved in config map.')
        return node_selector_args, return_code

  # Check if reservation id is valid. Shared function with cluster creation.
  node_selector_args, return_code = (
      get_capacity_node_selectors_from_capacity_type(args, capacity_type_str)
  )
  if return_code != 0:
    xpk_print('Unable to get node selectors from capacity type.')
    return node_selector_args, return_code

  return node_selector_args, return_code


def get_cluster_provisioner(args) -> str:
  metadata_configmap_name = f'{args.cluster}-{CLUSTER_METADATA_CONFIGMAP}'
  cluster_config_map = get_cluster_configmap(args, metadata_configmap_name)
  cluster_provisioner = 'gcloud'
  if not cluster_config_map is None:
    provisioner = cluster_config_map.get('provisioner')
    if not provisioner is None:
      cluster_provisioner = provisioner
  xpk_print(f'Cluster provisioner: {cluster_provisioner}')
  return cluster_provisioner
