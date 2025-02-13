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
from .capacity import AUTOPROVISIONING_CONFIG_MAXIMUM_KEY, AUTOPROVISIONING_CONFIG_VALUE
from .resources import ResourceManager
from .system_characteristics import (
    AcceleratorType,
    AcceleratorTypeToAcceleratorCharacteristics,
    SystemCharacteristics,
)


class Scheduler:
  """Handles workload scheduling logic."""

  def __init__(
      self,
      args,
      system: SystemCharacteristics,
      resource_manager: ResourceManager,
  ):
    self.args = args
    self.system = system
    self.resource_manager = resource_manager

  def create_accelerator_label(self) -> str:
    """Generates accelerator label.

    Returns:
      The accelerator label.
    """
    if self.system.accelerator_type == AcceleratorType['CPU']:
      return ''
    return (
        f'{AcceleratorTypeToAcceleratorCharacteristics[self.system.accelerator_type].accelerator_label}:'
        f' {self.system.gke_accelerator}'
    )

  def create_machine_label(self, autoprovisioning_enabled=False) -> str:
    """Generates machine label.

    Args:
      autoprovisioning_enabled: describes autoprovisioning enablement.

    Returns:
      The machine label.
    """
    if (
        self.system.accelerator_type == AcceleratorType['TPU']
        and not autoprovisioning_enabled
    ):
      return (
          f'{AcceleratorTypeToAcceleratorCharacteristics[self.system.accelerator_type].machine_label}:'
          f' {self.system.topology}'
      )
    return ''

  def check_if_workload_can_schedule(self) -> bool:
    """Check if workload can schedule based on the cluster resources (tpu_type and maximum VM in cluster).

    Returns:
      returns true if workload can schedule, otherwise returns false.
    """

    resources_configmap_name = (
        self.resource_manager.get_metadata_configmap_name()
    )
    cluster_config_map = self.resource_manager.get_resources_configmap()

    # Prevents workload creation failure for existing clusters with no ConfigMap
    if cluster_config_map is None:
      xpk_print(
          'No ConfigMap exist for cluster with the name'
          f' {resources_configmap_name}.'
      )
      return True

    # Check for GKE accelerator type:
    missing_gke_accelerator_type = False
    if not cluster_config_map.get(self.system.gke_accelerator):
      xpk_print(
          f'Gke Accelerator Type Check: {self.args.workload} is requesting'
          f' {self.system.gke_accelerator} but cluster only contains'
          f' {cluster_config_map.keys()}. '
      )
      missing_gke_accelerator_type = True
    elif (
        cluster_config_map[self.system.gke_accelerator]
        == AUTOPROVISIONING_CONFIG_VALUE
    ):
      max_chips_in_cluster = int(
          cluster_config_map[AUTOPROVISIONING_CONFIG_MAXIMUM_KEY]
      )
      num_chips_in_workload = (
          self.resource_manager.get_total_chips_requested_from_args()
      )

      if num_chips_in_workload > max_chips_in_cluster:
        xpk_print(
            f'{self.args.workload} is requesting {num_chips_in_workload} chips'
            f' but the cluster {self.args.cluster} supports up to'
            f' {max_chips_in_cluster}. Resize the cluster to support more chips'
            ' with `xpk cluster create --autoprovisioning-max-chips=X ...`'
        )
        return False
      return True

    # Check for device type
    missing_device_type = False
    if self.system.device_type not in cluster_config_map:
      xpk_print(
          f'Device Type Check: {self.args.workload} is requesting'
          f' {self.system.device_type} but cluster only contains'
          f' {cluster_config_map.keys()}. '
      )
      missing_device_type = True  # Track the missing device type

    if missing_device_type and missing_gke_accelerator_type:
      xpk_print(
          'Both Device Type and GKE Accelerator Type checks failed.'
          f' XPK will not create the workload {self.args.workload}.'
      )
      return False

    # Check if the size of the workload will fit in the cluster.
    max_vm_in_cluster = int(cluster_config_map[self.system.device_type])
    vm_required_by_workload = (
        self.args.num_nodes
        if self.system.accelerator_type == AcceleratorType['GPU']
        else self.args.num_slices * self.system.vms_per_slice
    )
    if vm_required_by_workload > max_vm_in_cluster:
      xpk_print(
          f'{self.args.workload} is requesting'
          f' {self.args.num_slices} slice/slices of {self.system.device_type},'
          f' which is {vm_required_by_workload} VMs, but the cluster only'
          f' contains {max_vm_in_cluster} VMs of {self.system.device_type}. XPK'
          ' will not create this workload.'
      )
      return False

    return True

  def get_cpu_affinity(self) -> str:
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
    if self.system.accelerator_type == AcceleratorType['CPU']:
      return yaml
    return ''

  def get_gpu_scheduler(self, autoprovisioning_args) -> tuple[str, int]:
    """Get gpu scheduler configuration.

    Args:
      args: user provided arguments for running the command.
      system: system characteristics.
      autoprovisioning_args: a string of arguments for Autoprovisioning.

    Returns:
      str: yaml containing gpu scheduler configuration
      int of 0 if successful and 1 otherwise.
    """

    if self.args.scheduler == 'gke.io/topology-aware-auto':
      return (
          f"""schedulingGates:
                - name: "{self.args.scheduler}-{self.args.workload}"
                """,
          0,
      )

    if self.args.scheduler == 'default-scheduler':
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
      return (
          gpu_scheduler_yaml.format(
              scheduler_name=self.args.scheduler,
              accelerator_label=self.create_accelerator_label(),
              machine_label=self.create_machine_label(),
              node_pool_name=f'{self.args.cluster}-np-0',
              autoprovisioning_args=autoprovisioning_args,
          ),
          0,
      )

    xpk_print(
        '--scheduler needs to be set as either `default-scheduler`'
        ' or `gke.io/topology-aware-auto` in order to schedule the'
        ' workloads on GPUs.'
    )
    return '', 1
