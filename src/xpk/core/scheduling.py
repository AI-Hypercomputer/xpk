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
  """Check if workload can schedule based on the cluster resources.

  This function validates that the resource requested by the user exists in the
  cluster's resource manifest (a ConfigMap) and that the requested quantity
  (e.g., number of VMs) does not exceed the available quantity.

  Args:
    args: User-provided arguments for running the command.
    system: System characteristics derived from the user's request.

  Returns:
    True if the workload can be scheduled, otherwise False.
  """
  resources_configmap_name = f'{args.cluster}-{CLUSTER_RESOURCES_CONFIGMAP}'
  cluster_config_map = get_cluster_configmap(args, resources_configmap_name)

  # If no ConfigMap exists, we cannot validate, so we optimistically proceed.
  # This maintains compatibility with older cluster setups.
  if cluster_config_map is None:
    xpk_print(
        f"Warning: Could not find resource ConfigMap '{resources_configmap_name}'. "
        "Proceeding without resource validation."
    )
    return True

  # The user-facing device type (e.g., 'v5litepod-32') is the single source
  # of truth for identifying the resource in the cluster's manifest.
  user_facing_device_type = args.tpu_type if args.tpu_type else args.device_type

  # --- Primary Validation ---
  # Check if the cluster's resource manifest contains an entry for the exact
  # device type the user requested. This is the only reliable existence check.
  if user_facing_device_type not in cluster_config_map:
    xpk_print(
        f"Device Type Check Failed: Workload '{args.workload}' is requesting "
        f"device type '{user_facing_device_type}', but the cluster's resource "
        f"manifest only contains entries for: {list(cluster_config_map.keys())}. "
        "The cluster may not be provisioned with this hardware type."
    )
    return False

  # --- Quantity Validation ---

  # Handle autoprovisioning capacity checks.
  if (
      cluster_config_map[user_facing_device_type]
      == AUTOPROVISIONING_CONFIG_VALUE
  ):
    max_chips_in_cluster = int(
        cluster_config_map.get(AUTOPROVISIONING_CONFIG_MAXIMUM_KEY, 0)
    )
    num_chips_in_workload = get_total_chips_requested_from_args(args, system)

    if num_chips_in_workload > max_chips_in_cluster:
      xpk_print(
          f"Chip Request Exceeds Limit: Workload '{args.workload}' requests "
          f"{num_chips_in_workload} chips, but the autoprovisioning cluster "
          f"'{args.cluster}' is configured for a maximum of {max_chips_in_cluster} chips."
      )
      return False
    return True # For autoprovisioning, chip count is sufficient.

  # For statically-sized clusters, check if the number of requested VMs fits.
  max_vm_in_cluster = int(cluster_config_map[user_facing_device_type])
  if system.accelerator_type == AcceleratorType['GPU']:
    vm_required_by_workload = args.num_nodes
  else:
    vm_required_by_workload = args.num_slices * system.vms_per_slice

  if vm_required_by_workload > max_vm_in_cluster:
    xpk_print(
        f"VM Request Exceeds Capacity: Workload '{args.workload}' requests "
        f"{vm_required_by_workload} VMs for {args.num_slices} slice(s) of type "
        f"'{user_facing_device_type}', but the cluster only has "
        f"{max_vm_in_cluster} VMs of that type available."
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


def create_tpu_machine_type(accelerator_type, system) -> str:
  """Generates TPU machine type..

  Args:
    accelerator_type: type of accelerator.
    system: system characteristics.

  Returns:
    The accelerator label.
  """
  if accelerator_type == AcceleratorType['TPU']:
    return f'{system.gce_machine_type}'
  return ''


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


def create_tpu_topology(
    accelerator_type, system, autoprovisioning_enabled: bool = False
) -> str:
  """Generates TPU topology.

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
    return f'{system.topology}'
  return ''
