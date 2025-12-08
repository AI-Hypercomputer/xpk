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

from enum import Enum

from .kueue_manager import get_installed_kueue_version, has_sub_slicing_enabled, has_super_slicing_enabled
from ..utils.feature_flags import FeatureFlags
from ..utils.topology import get_slice_topology_level
from ..utils.console import xpk_print
from ..utils.topology import is_topology_valid
from ..utils.execution_context import is_dry_run
from .capacity import AUTOPROVISIONING_CONFIG_MAXIMUM_KEY, AUTOPROVISIONING_CONFIG_VALUE
from .system_characteristics import (
    SUB_SLICING_TOPOLOGIES,
    AcceleratorType,
    SystemCharacteristics,
    create_accelerator_label,
    create_machine_label,
)
from packaging.version import Version

_SUB_SLICING_MINIMUM_KUEUE_VERSION = Version('0.13.0')
_SUPER_SLICING_MINIMUM_KUEUE_VERSION = Version('0.14.0')


class WorkloadScheduling(Enum):
  UNAVAILABLE = 0
  AVAILABLE = 1
  SUB_SLICING_AVAILABLE = 2
  SUPER_SLICING_AVAILABLE = 3


def check_if_workload_can_schedule(
    args,
    workload_system: SystemCharacteristics,
    cluster_system: SystemCharacteristics | None,
    resources_config_map: dict[str, str] | None,
) -> WorkloadScheduling:
  """Check if workload can schedule based on the cluster resources (tpu_type and maximum VM in cluster).

  Returns:
    returns WorkloadScheduling describing scheduling option.
  """
  if is_dry_run() and not cluster_system:
    xpk_print('Skipping workload scheduling validation in dry run.')
    return WorkloadScheduling.AVAILABLE

  if resources_config_map is None:
    xpk_print(
        "Skipping workload scheduling validation, because there's no Resources"
        ' ConfigMap in the cluster.'
    )
    return WorkloadScheduling.AVAILABLE

  if _is_cluster_set_up_for_nap(workload_system, resources_config_map):
    # Run total chip check when in autoprovisioning mode.
    max_chips_in_cluster = int(
        resources_config_map[AUTOPROVISIONING_CONFIG_MAXIMUM_KEY]
    )
    num_chips_in_workload = get_total_chips_requested_from_args(
        args, workload_system
    )

    if num_chips_in_workload > max_chips_in_cluster:
      xpk_print(
          f'{args.workload} is requesting {num_chips_in_workload} chips but'
          f' the cluster {args.cluster} supports up to {max_chips_in_cluster}.'
          '  Resize the cluster to support more chips with'
          ' `xpk cluster create --autoprovisioning-max-chips=X ...`'
      )
      return WorkloadScheduling.UNAVAILABLE
    return WorkloadScheduling.AVAILABLE

  if workload_system.device_type in resources_config_map:
    if _check_workload_size_fits(
        args,
        workload_system,
        max_vm_in_cluster=int(
            resources_config_map[workload_system.device_type]
        ),
    ):
      return WorkloadScheduling.AVAILABLE
    else:
      return WorkloadScheduling.UNAVAILABLE

  if cluster_system and _check_sub_slicing_availability(
      workload_system=workload_system, cluster_system=cluster_system
  ):
    if _check_workload_size_fits(
        args,
        workload_system,
        max_vm_in_cluster=int(resources_config_map[cluster_system.device_type]),
    ):
      return WorkloadScheduling.SUB_SLICING_AVAILABLE
    else:
      return WorkloadScheduling.UNAVAILABLE

  if cluster_system and _check_super_slicing_availability(
      workload_system=workload_system, cluster_system=cluster_system
  ):
    if _check_workload_size_fits(
        args,
        workload_system,
        max_vm_in_cluster=int(resources_config_map[cluster_system.device_type]),
    ):
      return WorkloadScheduling.SUPER_SLICING_AVAILABLE
    else:
      return WorkloadScheduling.UNAVAILABLE

  xpk_print(
      'Workload scheduling validation failed. XPK will not create the workload'
      f' {args.workload}.'
  )
  return WorkloadScheduling.UNAVAILABLE


def _is_cluster_set_up_for_nap(
    workload_system: SystemCharacteristics, resources_config_map: dict[str, str]
) -> bool:
  return (
      resources_config_map.get(workload_system.gke_accelerator, None)
      == AUTOPROVISIONING_CONFIG_VALUE
  )


def _check_workload_size_fits(
    args,
    workload_system: SystemCharacteristics,
    max_vm_in_cluster: int,
) -> bool:
  if workload_system.accelerator_type == AcceleratorType.GPU:
    vm_required_by_workload = args.num_nodes
  else:
    vm_required_by_workload = args.num_slices * workload_system.vms_per_slice

  if vm_required_by_workload > max_vm_in_cluster:
    xpk_print(
        f'{args.workload} is requesting {args.num_slices} slice/slices of'
        f' {workload_system.device_type}, which is'
        f' {vm_required_by_workload} VMs, but the cluster only contains'
        f' {max_vm_in_cluster} VMs of {workload_system.device_type}. XPK will'
        ' not create this workload.'
    )
    return False
  return True


def _check_sub_slicing_availability(
    workload_system: SystemCharacteristics,
    cluster_system: SystemCharacteristics,
) -> bool:
  if (
      (not FeatureFlags.SUB_SLICING_ENABLED)
      or (workload_system.gke_accelerator != cluster_system.gke_accelerator)
      or (not cluster_system.supports_sub_slicing)
      or (workload_system.topology not in SUB_SLICING_TOPOLOGIES)
  ):
    return False

  return_code, sub_slicing_enabled = has_sub_slicing_enabled()
  if return_code != 0 or not sub_slicing_enabled:
    return False

  return_code, current_version = get_installed_kueue_version(
      dry_run_version=_SUB_SLICING_MINIMUM_KUEUE_VERSION
  )

  return (
      return_code == 0
      and current_version is not None
      and current_version >= _SUB_SLICING_MINIMUM_KUEUE_VERSION
  )


def _check_super_slicing_availability(
    workload_system: SystemCharacteristics,
    cluster_system: SystemCharacteristics,
) -> bool:
  # TODO: b/465447813 - Add super-slicing workload topology validation.
  if (
      (not FeatureFlags.SUPER_SLICING_ENABLED)
      or (workload_system.gke_accelerator != cluster_system.gke_accelerator)
      or (not cluster_system.supports_super_slicing)
  ):
    return False

  return_code, sub_slicing_enabled = has_super_slicing_enabled()
  if return_code != 0 or not sub_slicing_enabled:
    return False

  return_code, current_version = get_installed_kueue_version(
      dry_run_version=_SUPER_SLICING_MINIMUM_KUEUE_VERSION
  )

  return (
      return_code == 0
      and current_version is not None
      and current_version >= _SUPER_SLICING_MINIMUM_KUEUE_VERSION
  )


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
  if system.accelerator_type == AcceleratorType.GPU:
    num_chips = system.vms_per_slice * system.chips_per_vm * args.num_nodes
  else:
    num_chips = system.vms_per_slice * system.chips_per_vm * args.num_slices

  return int(num_chips)


def get_cpu_affinity(accelerator_type: AcceleratorType) -> str:
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
  if accelerator_type == AcceleratorType.CPU:
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
        accelerator_label=create_accelerator_label(system),
        machine_label=create_machine_label(system),
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


def create_tpu_machine_type(system: SystemCharacteristics) -> str:
  if system.accelerator_type == AcceleratorType.TPU:
    return f'{system.gce_machine_type}'
  return ''


def create_tpu_topology(system: SystemCharacteristics) -> str:
  if system.accelerator_type == AcceleratorType.TPU:
    return f'{system.topology}'
  return ''


def create_sub_slicing_annotations(sub_slicing_topology: str) -> list[str]:
  """Generates subslicing annotations.

  Args:
    sub_slicing_topology: subslice topology.

  Returns:
    Annotations to be rendered in deployment yaml.
  """
  return [
      (
          'kueue.x-k8s.io/podset-required-topology:'
          f' "{get_slice_topology_level(sub_slicing_topology)}"'
      ),
      f'cloud.google.com/gke-tpu-slice-topology: {sub_slicing_topology}',
  ]


def create_placement_policy_label(
    system: SystemCharacteristics, super_slicing: bool
) -> str:
  name = get_placement_policy_name(system, super_slicing)
  return f'cloud.google.com/placement-policy-name: {name}'


def get_placement_policy_name(
    system: SystemCharacteristics, super_slicing: bool
) -> str:
  super_slicing_part = '-ss' if super_slicing else ''
  return f'{system.device_type}-{system.topology}{super_slicing_part}-placement-policy'


def is_placement_policy_supported(system: SystemCharacteristics) -> bool:
  return system.requires_workload_policy and is_topology_valid(system.topology)
