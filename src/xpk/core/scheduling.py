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
from .resources import CLUSTER_RESOURCES_CONFIGMAP, get_cluster_configmap
from .system_characteristics import (
    AcceleratorType,
    AcceleratorTypeToAcceleratorCharacteristics,
    SystemCharacteristics,
)


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

  return int(num_chips)


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
