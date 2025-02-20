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

from ..utils.console import get_user_input, xpk_print
from .capacity import (
    AUTOPROVISIONING_CONFIG_VALUE,
    H100_MEGA_DEVICE_TYPE,
    CapacityType,
    get_capacity_arguments_from_capacity_type,
    get_capacity_type,
    print_reservations,
)
from .commands import run_command_for_value, run_commands
from .gcloud_context import GkeServerConfig, zone_to_region
from .resources import (
    CLUSTER_CONFIGMAP_YAML,
    CLUSTER_RESOURCES_CONFIGMAP,
    check_cluster_resources,
    create_or_update_cluster_configmap,
)
from .system_characteristics import AcceleratorType

CLOUD_PLATFORM_AUTH_SCOPE_URL = (
    '"https://www.googleapis.com/auth/cloud-platform"'
)


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
      resources_yml = CLUSTER_CONFIGMAP_YAML.format(
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
      if device_type == H100_MEGA_DEVICE_TYPE:
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
      f' --region={zone_to_region(args.zone)} --format="value(locations)"'
  )
  return_code, nodepool_zone = run_command_for_value(
      command, 'Get Node Pool Zone', args
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
    return int(max_return_code)
  return 0


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
