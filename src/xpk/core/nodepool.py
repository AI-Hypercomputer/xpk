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
    CapacityManager,
    CapacityType,
    DeviceType,
)
from .commands import run_command_for_value, run_commands
from .gcloud_context import GCloudContextManager, GKEVersionManager
from .resources import ResourceManager
from .system_characteristics import AcceleratorType

CLOUD_PLATFORM_AUTH_SCOPE_URL = (
    '"https://www.googleapis.com/auth/cloud-platform"'
)


class NodePoolManager:
  """Manages GKE Node Pool operations including creation, deletion, and configuration."""

  def __init__(
      self,
      args,
      system,
      resource_manager: ResourceManager,
      capacity_manager: CapacityManager,
  ):
    self.args = args
    self.system = system
    self.resource_manager = resource_manager
    self.capacity_manager = capacity_manager

  def create_node_pool(self, gke_node_pool_version) -> int:
    """Run the Create GKE Node Pool request.

    Args:
      gke_node_pool_version: GKE version to use to create node pools.

    Returns:
      0 if successful and 1 otherwise.
    """
    device_type = (
        self.args.tpu_type if self.args.tpu_type else self.args.device_type
    )
    xpk_print(
        f'Creating {self.args.num_slices} node pool or pools of {device_type}\n'
        f'We assume that the underlying system is: {self.system}'
    )

    existing_node_pool_names, return_code = self.get_all_nodepools()
    if return_code > 0:
      xpk_print('Listing all node pools failed!')
      return return_code

    capacity_type, return_code = self.capacity_manager.get_capacity_type()
    if return_code > 0:
      xpk_print('Parsing capacity type failed!')
      return return_code

    if capacity_type == CapacityType.UNKNOWN:
      return_code = self.capacity_manager.print_reservations()
      xpk_print(
          'ERROR: User needs to provide the capacity type. Please specify one'
          ' of the following `--reservation=$RESERVATION_NAME`, `--on-demand`'
          ' or `--spot`. See the above list of reservations to choose from.'
      )
      if return_code > 0:
        xpk_print('Listing all reservations failed!')
      return 1

    capacity_args, return_code = self.capacity_manager.get_capacity_arguments(
        capacity_type
    )
    if return_code > 0:
      xpk_print('Parsing capacity arguments failed!')
      return return_code

    if self.system.accelerator_type == AcceleratorType['GPU']:
      xpk_print(
          f'Creating 1 node pool with {self.args.num_nodes} nodes of'
          f' {self.system.device_type}\nUnderlyingly, we assume that means:'
          f' {self.system}'
      )
      desired_node_pool_names = [f'{self.args.cluster}-np-0']
    else:
      xpk_print(
          f'Creating {self.args.num_slices} node pool or pools of'
          f' {self.system.device_type}\nUnderlyingly, we assume that means:'
          f' {self.system}'
      )
      desired_node_pool_names = [
          f'{self.args.cluster}-np-{slice_num}'
          for slice_num in range(self.args.num_slices)
      ]

    node_pools_to_remain, delete_commands, delete_task_names = [], [], []
    if existing_node_pool_names:
      return_code, existing_node_pool_zone = self.get_nodepool_zone(
          existing_node_pool_names[0]
      )
      if return_code != 0:
        return 1

      if existing_node_pool_zone and existing_node_pool_zone != self.args.zone:
        xpk_print(
            f'Cluster {self.args.cluster} already has nodepools in zone:'
            f' {existing_node_pool_zone}. Use the same zone to update nodepools'
            ' in the cluster.'
        )
        return 1

      node_pools_to_delete = self.get_node_pools_to_delete(
          existing_node_pool_names, desired_node_pool_names
      )
      for node_pool_name in existing_node_pool_names:
        if not node_pool_name.startswith(f'{self.args.cluster}-np-'):
          continue

        if node_pool_name in node_pools_to_delete:
          delete_commands.append(
              'gcloud beta container node-pools delete'
              f' {node_pool_name} --cluster={self.args.cluster}'
              f' --zone={GCloudContextManager.zone_to_region(self.args.zone)}'
              f' --project={self.args.project} --quiet'
          )
          delete_task_names.append(f'NodepoolDelete-{node_pool_name}')
        else:
          node_pools_to_remain.append(node_pool_name)

    # Deletion of nodepools should happen before attempting to create new nodepools for the case
    # when cluster is getting updated from 'x' device_type/gke_accelerator to 'y' device_type/gke_accelerator.
    # In that case, '{args.cluster}-np-i' nodepool will be re-created for 'y' device_type/gke_accelerator.
    if delete_commands:
      will_delete = True
      if node_pools_to_delete and not self.args.force:
        will_delete = get_user_input(
            f'Planning to delete {len(node_pools_to_delete)} node pools'
            f' including {node_pools_to_delete}. \nDo you wish to delete: y'
            ' (yes) / n (no):\n'
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
          dry_run=self.args.dry_run,
      )
      if max_return_code != 0:
        xpk_print(f'Delete Nodepools returned ERROR {max_return_code}')
        return 1

      # Update {args.cluster}-{_CLUSTER_RESOURCES_CONFIGMAP} ConfigMap to 'y': '0'
      # and remove 'x' from the ConfigMap when cluster is getting updated from
      # 'x' device_type/gke_accelerator to 'y' device_type/gke_accelerator.
      if not node_pools_to_remain:
        resources_data = (
            f'{self.system.gke_accelerator}: {AUTOPROVISIONING_CONFIG_VALUE}'
            if self.args.enable_autoprovisioning
            else f'{device_type}: "0"'
        )
        resources_configmap_name = (
            self.resource_manager.get_resources_configmap_name()
        )
        resources_yml = self.resource_manager.create_configmap_string(
            resources_data
        )
        configmap_yml = {resources_configmap_name: resources_yml}
        return_code = self.resource_manager.create_or_update_cluster_configmap(
            configmap_yml
        )
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
          f' --region={GCloudContextManager.zone_to_region(self.args.zone)}'
          f' --cluster={self.args.cluster}'
          f' --project={self.args.project} --node-locations={self.args.zone}'
          f' --machine-type={self.system.gce_machine_type}'
          f' --host-maintenance-interval={self.args.host_maintenance_interval}'
          f' {capacity_args}'
          ' --enable-gvnic'
          f' {self.args.custom_nodepool_arguments}'
      )

      if self.system.accelerator_type == AcceleratorType['TPU']:
        command += (
            f' --node-version={gke_node_pool_version} '
            f'--num-nodes={self.system.vms_per_slice} '
            '--placement-type=COMPACT --max-pods-per-node 15 '
            f'--scopes=storage-full,gke-default,{CLOUD_PLATFORM_AUTH_SCOPE_URL} '
            f'--tpu-topology={self.system.topology} {self.args.custom_tpu_nodepool_arguments}'
        )
      elif self.system.accelerator_type == AcceleratorType['GPU']:
        subnet_prefix = f'{self.args.cluster}-{GCloudContextManager.zone_to_region(self.args.zone)}'
        command += (
            f' --num-nodes={self.args.num_nodes}'
            ' --accelerator'
            f' type={self.system.gke_accelerator},count={str(self.system.chips_per_vm)},gpu-driver-version=latest'
            ' --no-enable-autoupgrade '
            f' --scopes={CLOUD_PLATFORM_AUTH_SCOPE_URL} --additional-node-network'
            f' network={self.args.cluster}-net-1,subnetwork={subnet_prefix}-sub-1'
            ' --additional-node-network'
            f' network={self.args.cluster}-net-2,subnetwork={subnet_prefix}-sub-2'
            ' --additional-node-network'
            f' network={self.args.cluster}-net-3,subnetwork={subnet_prefix}-sub-3'
            ' --additional-node-network'
            f' network={self.args.cluster}-net-4,subnetwork={subnet_prefix}-sub-4'
        )
        if device_type == DeviceType.H100.value:
          command += (
              ' --additional-node-network'
              f' network={self.args.cluster}-net-5,subnetwork={subnet_prefix}-sub-5'
              ' --additional-node-network'
              f' network={self.args.cluster}-net-6,subnetwork={subnet_prefix}-sub-6'
              ' --additional-node-network'
              f' network={self.args.cluster}-net-7,subnetwork={subnet_prefix}-sub-7'
              ' --additional-node-network'
              f' network={self.args.cluster}-net-8,subnetwork={subnet_prefix}-sub-8'
              ' --max-pods-per-node=32'
          )
      elif self.system.accelerator_type == AcceleratorType['CPU']:
        command += (
            f' --num-nodes={self.system.vms_per_slice} '
            f'--scopes=storage-full,gke-default,{CLOUD_PLATFORM_AUTH_SCOPE_URL}'
        )

      create_commands.append(command)
      create_task_names.append(f'NodepoolCreate-{node_pool_name}')

    if self.args.enable_pathways:
      # Pathways needs CPU nodepools in addition to TPU nodepools
      for node_pool_name in ['cpu-user-np', 'cpu-rm-np', 'cpu-proxy-np']:
        if node_pool_name in existing_node_pool_names:
          continue

        create_commands.append(
            'gcloud beta container node-pools create'
            f' {node_pool_name} --node-version={gke_node_pool_version} --cluster={self.args.cluster} --project={self.args.project} --node-locations={self.args.zone} --region={GCloudContextManager.zone_to_region(self.args.zone)} --num-nodes=1'
            f' --machine-type={self.args.pathways_gce_machine_type} --scopes=storage-full,gke-default,{CLOUD_PLATFORM_AUTH_SCOPE_URL} --enable-autoscaling'
            ' --min-nodes=1 --max-nodes=20'
        )
        create_task_names.append(f'NodepoolCreate-{node_pool_name}')

    for cmd, task in zip(create_commands, create_task_names):
      xpk_print(f'To complete {task} we are executing {cmd}')

    max_return_code = run_commands(
        create_commands,
        'Create Nodepools',
        create_task_names,
        dry_run=self.args.dry_run,
    )
    if max_return_code != 0:
      xpk_print(f'Create Nodepools returned ERROR {max_return_code}')
      return 1

    xpk_print('Create or delete node pool request complete.')
    return 0

  def get_all_nodepools(self) -> tuple[list[str], int]:
    """Gets all the nodepools associated with the cluster / project / region.

    Returns:
      List of nodepools and 0 if successful and 1 otherwise.
    """
    command = (
        'gcloud beta container node-pools list'
        ' --cluster'
        f' {self.args.cluster} --project={self.args.project} --region={GCloudContextManager.zone_to_region(self.args.zone)}'
        ' --format="csv[no-heading](name)"'
    )
    return_code, raw_nodepool_output = run_command_for_value(
        command, 'Get All Node Pools', self.args
    )
    if return_code != 0:
      xpk_print(f'Get All Node Pools returned ERROR {return_code}')
      return [], 1

    return raw_nodepool_output.splitlines(), 0

  def get_nodepool_zone(self, nodepool_name) -> tuple[int, str | None]:
    """Return zone in which nodepool exists in the cluster.

    Args:
      nodepool_name: name of nodepool.

    Returns:
      Tuple of int, str where
      int is the return code - 0 if successful, 1 otherwise.
      str is the zone of nodepool.
    """
    command = (
        f'gcloud beta container node-pools describe {nodepool_name}'
        f' --cluster {self.args.cluster} --project={self.args.project}'
        f' --region={GCloudContextManager.zone_to_region(self.args.zone)} --format="value(locations)"'
    )
    return_code, nodepool_zone = run_command_for_value(
        command, 'Get Node Pool Zone', self.args
    )
    if return_code != 0:
      xpk_print(f'Get Node Pool Zone returned ERROR {return_code}')
      return 1, None

    return 0, nodepool_zone.strip()

  def get_node_pools_to_delete(
      self, existing_node_pool_names, desired_node_pool_names
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
    resource_manager = ResourceManager(self.args, self.system)
    check_resource, is_requested_resource_in_cluster = (
        resource_manager.check_cluster_resources()
    )
    for existing_node_pool_name in existing_node_pool_names:
      # Deletion logic would leave behind any Pathways CPU nodepools.
      if existing_node_pool_name.find(f'{self.args.cluster}-np-') != 0:
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

  def get_node_pool_version(
      self, gke_server_config: GKEVersionManager
  ) -> tuple[int, str | None]:
    """Determine the gke node pool version for the node pool.

    Args:
      gke_server_config: holds valid gke versions and recommended default version.

    Returns:
      Tuple of
      int: 0 if successful and 1 otherwise.
      str: gke control plane version to use.
    """

    # By default use the current gke master version for creating node pools.
    command_description = 'Determine current gke master version'
    command = (
        f'gcloud beta container clusters describe {self.args.cluster} --region'
        f' {GCloudContextManager.zone_to_region(self.args.zone)} --project'
        f' {self.args.project} --format="value(currentMasterVersion)"'
    )

    return_code, current_gke_master_version = run_command_for_value(
        command, command_description, self.args
    )
    if return_code != 0:
      xpk_print(
          f'Unable to get server config for command: {command_description}.'
      )
      return return_code, None

    # Override with user provide gke version if specified.
    if self.args.gke_version is not None:
      node_pool_gke_version = self.args.gke_version
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
          f'Planned node pool version {node_pool_gke_version} is not supported'
          f' in valid version {gke_server_config.valid_versions}\nPlease adjust'
          ' the gke version using --gke-version=x or remove the arg and depend'
          f' on xpk default of {current_gke_master_version}'
      )
      return 1, None
    return 0, node_pool_gke_version
