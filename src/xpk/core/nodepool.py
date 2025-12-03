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

from typing import List

from ..utils.feature_flags import FeatureFlags
from ..utils.console import ask_for_user_consent, xpk_print
from .scheduling import get_placement_policy_name, is_placement_policy_supported
from .capacity import (
    AUTOPROVISIONING_CONFIG_VALUE,
    H100_MEGA_DEVICE_TYPE,
    CapacityType,
    get_capacity_arguments_from_capacity_type,
    get_capacity_type,
    print_reservations,
)
from .commands import run_command_for_value, run_commands, FailedCommand
from .gcloud_context import GkeServerConfig, get_cluster_location, zone_to_region
from .resources import (
    ConfigMapType,
    check_cluster_resources,
    update_cluster_configmap,
)
from .system_characteristics import AcceleratorType, SystemCharacteristics


CLOUD_PLATFORM_AUTH_SCOPE_URL = (
    '"https://www.googleapis.com/auth/cloud-platform"'
)

OLDER_PATHWAYS_CPU_NP_TO_DELETE = ['cpu-rm-np', 'cpu-proxy-np', 'cpu-user-np']


def run_gke_node_pool_create_command(
    args, system: SystemCharacteristics, gke_node_pool_version: str
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
  if system.accelerator_type == AcceleratorType.TPU:
    max_nodes = system.vms_per_slice
  else:
    max_nodes = 1000
  capacity_args, return_code = get_capacity_arguments_from_capacity_type(
      args, capacity_type, max_nodes, system.accelerator_type
  )
  if return_code > 0:
    xpk_print('Parsing capacity arguments failed!')
    return return_code

  desired_node_pool_count = (
      1 if system.accelerator_type == AcceleratorType.GPU else args.num_slices
  )
  message = (
      (
          f'Creating 1 node pool with {args.num_nodes} nodes of'
          f' {system.device_type}\nUnderlyingly, we assume that means: {system}'
      )
      if system.accelerator_type == AcceleratorType.GPU
      else (
          f'Creating {args.num_slices} node pool or pools of'
          f' {system.device_type}\nUnderlyingly, we assume that means: {system}'
      )
  )
  xpk_print(message)
  desired_node_pool_names = get_desired_node_pool_names(
      existing_node_pool_names, args.cluster, desired_node_pool_count
  )

  node_pools_to_delete = []
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
      if (
          node_pool_name.find(f'{args.cluster}-np-') != 0
          and node_pool_name not in OLDER_PATHWAYS_CPU_NP_TO_DELETE
      ):
        continue

      if node_pool_name in node_pools_to_delete:
        command = (
            'gcloud beta container node-pools delete'
            f' {node_pool_name} --cluster={args.cluster}'
            f' --zone={get_cluster_location(args.project, args.cluster, args.zone)}'
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
                f' {node_pool_name} --cluster={args.cluster} --location={get_cluster_location(args.project, args.cluster, args.zone)} --project={args.project} --quiet'
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
    if node_pools_to_delete and not ask_for_user_consent(
        f'Planning to delete {len(node_pools_to_delete)} node pools including'
        f' {node_pools_to_delete}. \nDo you wish to delete?'
    ):
      xpk_print(
          'You have requested to not delete the existing nodepools in the'
          ' cluster. There will be no change to the cluster.'
      )
      return 1

    for i, command in enumerate(delete_commands):
      xpk_print(
          f'To complete {delete_task_names[i]} we are executing {command}'
      )
    maybe_failure = run_commands(
        delete_commands,
        'Delete Nodepools',
        delete_task_names,
    )
    if maybe_failure is not None:
      xpk_print(f'Delete Nodepools returned ERROR {maybe_failure.return_code}')
      return 1

  # Enable Workload Identity on existing Nodepools
  if update_WI_commands:
    will_update_WI = not node_pools_to_update_WI or ask_for_user_consent(
        'Planning to enable Workload Identity Federation on'
        f' {len(node_pools_to_update_WI)} existing node pools including'
        f' {node_pools_to_update_WI}. This immediately enables Workload'
        ' Identity Federation for GKE for any workloads running in the node'
        ' pool. Also, xpk does not support disabling Workload Identity on'
        ' clusters that have it enabled already \nDo you wish to update?'
    )
    if will_update_WI:
      for i, command in enumerate(update_WI_commands):
        xpk_print(
            f'To complete {update_WI_task_names[i]} we are executing {command}'
        )
      maybe_failure = run_commands(
          update_WI_commands,
          'Enable Workload Identity on existing Nodepools',
          update_WI_task_names,
      )
      if maybe_failure is not None:
        xpk_print(
            'Enable Workload Identity on existing Nodepools returned ERROR'
            f' {maybe_failure.return_code}'
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
      return_code = update_cluster_configmap(
          cluster_name=args.cluster,
          config_map_type=ConfigMapType.RESOURCES,
          data=resources_data,
      )
      if return_code != 0:
        return 1

  placement_args = ''
  if is_placement_policy_supported(system):
    super_slicing = FeatureFlags.SUPER_SLICING_ENABLED and args.super_slicing
    placement_policy = get_placement_policy_name(
        system,
        super_slicing,
    )
    ensure_resource_policy_exists(
        resource_policy_name=placement_policy,
        project=args.project,
        zone=args.zone,
        topology=system.topology,
        super_slicing=super_slicing,
    )
    placement_args = f' --placement-policy={placement_policy}'

  create_commands = []
  create_task_names = []
  for node_pool_name in desired_node_pool_names:
    if node_pool_name in node_pools_to_remain:
      continue
    command = (
        'gcloud beta container node-pools create'
        f' {node_pool_name}'
        f' --location={get_cluster_location(args.project, args.cluster, args.zone)}'
        f' --cluster={args.cluster}'
        f' --project={args.project} --node-locations={args.zone}'
        f' --machine-type={system.gce_machine_type}'
        f' --host-maintenance-interval={args.host_maintenance_interval}'
        f' {capacity_args}'
        f'{placement_args}'
        ' --enable-gvnic'
    )
    if system.accelerator_type == AcceleratorType.TPU:
      command += f' --node-version={gke_node_pool_version}'
      if capacity_type == CapacityType.FLEX_START:
        command += ' --num-nodes=0'
      else:
        command += f' --num-nodes={system.vms_per_slice}'
      command += (
          f' --scopes=storage-full,gke-default,{CLOUD_PLATFORM_AUTH_SCOPE_URL}'
      )

      # --tpu-topology should not be set for single-host node pools
      if system.vms_per_slice > 1:
        # --placement-type=COMPACT enables group placement policy which
        # is mutually exclusive with workload policy, --tpu-topology should
        # also not be passed when workload policy is used
        if not system.requires_workload_policy:
          command += ' --placement-type=COMPACT'
          command += f' --tpu-topology={system.topology}'
        command += ' --max-pods-per-node 15'
        command += f' {args.custom_tpu_nodepool_arguments}'
    elif system.accelerator_type == AcceleratorType.GPU:
      subnet_prefix = (
          f'{args.cluster}-{get_cluster_location(args.project, args.cluster, args.zone)}'
      )
      if capacity_type == CapacityType.FLEX_START:
        command += ' --num-nodes=0'
      else:
        command += f' --num-nodes={args.num_nodes}'
      command += (
          ' --accelerator'
          f' type={system.gke_accelerator},count={str(system.chips_per_vm)},gpu-driver-version=latest'
          f' --scopes={CLOUD_PLATFORM_AUTH_SCOPE_URL}'
      )
      if device_type == H100_MEGA_DEVICE_TYPE:
        for i in range(1, 9):
          command += (
              ' --additional-node-network'
              f' network={args.cluster}-net-{i},subnetwork={subnet_prefix}-sub-{i}'
          )
        command += ' --max-pods-per-node=32'
    elif system.accelerator_type == AcceleratorType.CPU:
      if capacity_type == CapacityType.FLEX_START:
        command += ' --num-nodes=0'
      else:
        command += f' --num-nodes={system.vms_per_slice}'
      command += (
          f' --scopes=storage-full,gke-default,{CLOUD_PLATFORM_AUTH_SCOPE_URL}'
      )

    if args.enable_workload_identity or args.enable_gcsfuse_csi_driver:
      command += ' --workload-metadata=GKE_METADATA'

    command += f' {args.custom_nodepool_arguments}'

    task = f'NodepoolCreate-{node_pool_name}'
    create_commands.append(command)
    create_task_names.append(task)

  desired_pw_cpu_node_pools = ['cpu-np']
  if args.enable_pathways:
    # Pathways needs CPU nodepools in addition to TPU nodepools
    for node_pool_name in desired_pw_cpu_node_pools:
      if node_pool_name in existing_node_pool_names:
        continue
      command = (
          'gcloud beta container node-pools create'
          f' {node_pool_name} --node-version={gke_node_pool_version} --cluster={args.cluster} --project={args.project} --node-locations={args.zone} --location={get_cluster_location(args.project, args.cluster, args.zone)} --num-nodes=1'
          f' --machine-type={args.pathways_gce_machine_type} --scopes=storage-full,gke-default,{CLOUD_PLATFORM_AUTH_SCOPE_URL} --enable-autoscaling'
          ' --min-nodes=1 --max-nodes=20'
      )
      task = f'NodepoolCreate-{node_pool_name}'
      create_commands.append(command)
      create_task_names.append(task)

  for i, command in enumerate(create_commands):
    xpk_print(f'To complete {create_task_names[i]} we are executing {command}')
  maybe_failure = run_commands(
      create_commands,
      'Create Nodepools',
      create_task_names,
  )
  if maybe_failure is not None:
    display_nodepool_creation_error(maybe_failure)
    return 1

  xpk_print('Create or delete node pool request complete.')
  return 0


def display_nodepool_creation_error(maybe_failure: FailedCommand) -> None:
  """Display nodepool creation errors to the user."""

  xpk_print(f'Create Nodepools returned ERROR {maybe_failure.return_code}')
  try:
    with open(maybe_failure.logfile, 'r', encoding='utf-8') as f:
      contents = f.read()
    error_marker = 'finished with error:'
    error = contents[contents.index(error_marker) + len(error_marker) :].strip()
    # the longest error we're expecting to see is 256 characters + np name
    max_error_display_length = 400
    xpk_print(f'Nodepool creation error: {error[:max_error_display_length]}')
    if (
        error.find('lack of capacity') != -1
        or error.find('Requested resource is exhausted') != -1
    ):
      xpk_print('NOTE: this error might be caused by a stockout')
  except (FileNotFoundError, IOError, ValueError):
    # silently ignore any log parsing errors
    pass


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
  xpk_print('Existing node pool names ', existing_node_pool_names)

  for existing_node_pool_name in existing_node_pool_names:
    # Nodepools will be deleted in two scenarios:
    # Scenario 1: Cluster exists with 3 nodepools of 'x' device_type/gke_accelerator and now we are updating
    # the cluster to 2 nodepools of 'x' device_type/gke_accelerator. In this case, we will delete
    # '{args.cluster}-np-2' from the cluster.
    # Scenario 2: Cluster exists with 2 nodepools of 'x' device_type/gke_accelerator and now we are updating
    # the cluster to 2 nodepools of 'y' device_type/gke_accelerator. In this case, we will delete
    # '{args.cluster}-np-0' and '{args.cluster}-np-1' from the cluster.
    # Scenario 3: Deletes older Pathways CPU nodepools named cpu-rm-np, cpu-proxy-np and cpu-user-np

    if existing_node_pool_name in OLDER_PATHWAYS_CPU_NP_TO_DELETE:
      node_pools_to_delete.append(existing_node_pool_name)
      xpk_print(
          'Upgrading Pathways version on the cluster. Deleting older pathways'
          ' nodepool ',
          existing_node_pool_name,
      )

    if existing_node_pool_name.find(f'{args.cluster}-np-') != 0:
      continue
    if existing_node_pool_name not in desired_node_pool_names or (
        check_resource and not is_requested_resource_in_cluster
    ):
      node_pools_to_delete.append(existing_node_pool_name)

  return node_pools_to_delete


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
      f' {args.cluster} --project={args.project} '
      f'--location={get_cluster_location(args.project, args.cluster, args.zone)}'
      ' --format="csv[no-heading](name)"'
  )
  return_code, raw_nodepool_output = run_command_for_value(
      command, 'Get All Node Pools'
  )
  if return_code != 0:
    xpk_print(f'Get All Node Pools returned ERROR {return_code}')
    return [], 1

  return raw_nodepool_output.splitlines(), 0


def get_nodepool_zone(args, nodepool_name) -> tuple[int, str | None]:
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
      f' --location={get_cluster_location(args.project, args.cluster, args.zone)} --format="value(locations)"'
  )
  return_code, nodepool_zone = run_command_for_value(
      command, 'Get Node Pool Zone', dry_run_return_val=args.zone
  )
  if return_code != 0:
    xpk_print(f'Get Node Pool Zone returned ERROR {return_code}')
    return 1, None

  return 0, nodepool_zone.strip()


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
      f'gcloud beta container clusters describe {args.cluster} --location'
      f' {get_cluster_location(args.project, args.cluster, args.zone)} --project'
      f' {args.project} --format="value(currentMasterVersion)"'
  )

  return_code, current_gke_master_version = run_command_for_value(
      command, command_description
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


def get_nodepool_workload_metadata_mode(
    args, nodepool_name
) -> tuple[int, str | None]:
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
      f' --location={get_cluster_location(args.project, args.cluster, args.zone)} --format="value(config.workloadMetadataConfig.mode)"'
  )
  return_code, nodepool_WI_mode = run_command_for_value(
      command, 'Get Node Pool Workload Identity Metadata Mode'
  )
  if return_code != 0:
    xpk_print(
        'Get Node Pool Workload Identity Metadata Mode returned ERROR'
        f' {return_code}'
    )
    return 1, None

  return 0, nodepool_WI_mode.strip()


def get_desired_node_pool_names(
    existing_node_pool_names: List[str],
    cluster_name: str,
    desired_node_pool_count: int,
) -> List[str]:
  cluster_node_pools = [
      np
      for np in existing_node_pool_names
      if np.startswith(f'{cluster_name}-np-')
  ]
  result = set(cluster_node_pools[:desired_node_pool_count])
  i = 0
  while len(result) < desired_node_pool_count:
    result.add(f'{cluster_name}-np-{i}')
    i += 1
  return list(sorted(result))


def ensure_resource_policy_exists(
    resource_policy_name: str,
    project: str,
    zone: str,
    topology: str,
    super_slicing: bool,
) -> None:
  return_code, _ = run_command_for_value(
      (
          'gcloud compute resource-policies describe'
          f' {resource_policy_name}'
          f' --project={project}'
          f' --region={zone_to_region(zone)}'
      ),
      'Retrieve resource policy',
  )

  if return_code == 0:
    return

  # TODO: b/465696970 - Verify the flag below before launching SUPER_SLICING:
  accelerator_topology_mode = (
      ' --accelerator-topology-mode=PROVISION_ONLY' if super_slicing else ''
  )
  return_code, _ = run_command_for_value(
      (
          'gcloud compute resource-policies create workload-policy'
          f' {resource_policy_name} --project={project} --region={zone_to_region(zone)} --type=HIGH_THROUGHPUT'
          f' --accelerator-topology={topology}{accelerator_topology_mode}'
      ),
      'Create resource policy',
  )

  if return_code != 0:
    raise RuntimeError('Unable to create resource policy')
