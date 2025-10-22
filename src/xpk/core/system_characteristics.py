"""
Copyright 2023 Google LLC

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
from ..utils.topology import get_topology_product


AcceleratorType = {'TPU': 1, 'GPU': 2, 'CPU': 3}


@dataclass
class AcceleratorCharacteristics:
  resource_type: str
  accelerator_label: str
  machine_label: str


AcceleratorTypeToAcceleratorCharacteristics = {
    AcceleratorType['TPU']: AcceleratorCharacteristics(
        resource_type='google.com/tpu',
        accelerator_label='cloud.google.com/gke-tpu-accelerator',
        machine_label='cloud.google.com/gke-tpu-topology',
    ),
    AcceleratorType['GPU']: AcceleratorCharacteristics(
        resource_type='nvidia.com/gpu',
        accelerator_label='cloud.google.com/gke-accelerator',
        machine_label='cloud.google.com/gce-machine-type',
    ),
    AcceleratorType['CPU']: AcceleratorCharacteristics(
        resource_type='cpu',
        accelerator_label='',
        machine_label='cloud.google.com/gke-nodepool',
    ),
}


@dataclass
class SystemCharacteristics:
  """Contains the defining characteristics of a specific accelerator system.

  This dataclass holds the hardware and configuration details for a given
  accelerator type, such as its topology, machine type, and chip count. It
  provides a standardized way to access system-specific information throughout
  the application.

  Attributes:
    topology: The physical or logical layout of the accelerator chips (e.g.,
      '2x2x1' for TPUs, 'N/A' for single-VM GPUs).
    vms_per_slice: The number of Virtual Machines that constitute a single
      accelerator slice.
    gke_accelerator: The name of the accelerator as recognized by GKE (e.g.,
      'nvidia-l4', 'tpu7x').
    gce_machine_type: The GCE machine type that hosts the accelerator (e.g.,
      'g2-standard-12').
    chips_per_vm: The number of accelerator chips attached to a single VM.
    accelerator_type: The category of the accelerator (e.g., TPU, GPU, CPU)
      from the AcceleratorType enum.
    device_type: A user-facing name for the specific hardware configuration
      (e.g., 'l4-1', 'h100-80gb-8').
    supports_sub_slicing: Whether the Sub-slicing feature is supported.
    requires_workload_policy: A boolean indicating if a GCE resource
      workload policy is required. This is automatically set to True for GPUs.
  """

  topology: str
  vms_per_slice: int
  gke_accelerator: str
  gce_machine_type: str
  chips_per_vm: int
  accelerator_type: int  # TODO: use enums
  device_type: str
  supports_sub_slicing: bool
  requires_workload_policy: bool = False

  def __post_init__(self):
    if self.accelerator_type == AcceleratorType['GPU']:
      self.requires_workload_policy = True


def get_system_characteristics(
    args,
) -> tuple[SystemCharacteristics | None, int]:
  """Get system characteristics based on user provided arguments.

  Args:
    args: user provided arguments for running the command.

  Returns:
    Tuple with string with the system characteristics and
    int of 0 if successful and 1 otherwise.
  """
  device_type = args.tpu_type if args.tpu_type else args.device_type
  return get_system_characteristics_by_device_type(device_type)


def get_system_characteristics_by_device_type(
    device_type,
) -> tuple[SystemCharacteristics | None, int]:
  """Get system characteristics based on device_type.

  Args:
    device_type: device_type for running the command.

  Returns:
    Tuple with string with the system characteristics and
    int of 0 if successful and 1 otherwise.
  """
  if device_type in UserFacingNameToSystemCharacteristics:
    return UserFacingNameToSystemCharacteristics[device_type], 0
  else:
    return None, 1


def get_tpu_system_characteristics_map(
    prefix: str,
    tensorcores_per_chip: int,
    gke_accelerator: str,
    machine_type: str,
    supported_topologies: list[str],
    supports_sub_slicing: bool,
    requires_workload_policy: bool = False,
) -> dict[str, SystemCharacteristics]:
  system_characteristics_map = {}
  for topology in supported_topologies:
    chips_per_vm = compute_chips_per_vm(topology)
    vms_per_slice = compute_vms_per_slice(topology)
    num_tensorcores = compute_num_tensorcores(tensorcores_per_chip, topology)
    system = SystemCharacteristics(
        topology=topology,
        vms_per_slice=vms_per_slice,
        gke_accelerator=gke_accelerator,
        gce_machine_type=machine_type,
        chips_per_vm=chips_per_vm,
        accelerator_type=AcceleratorType['TPU'],
        device_type=f'{prefix}-{num_tensorcores}',
        requires_workload_policy=requires_workload_policy,
        supports_sub_slicing=supports_sub_slicing,
    )
    system_characteristics_map[f'{prefix}-{topology}'] = system
    system_characteristics_map[f'{prefix}-{num_tensorcores}'] = system

  return system_characteristics_map


def compute_chips_per_vm(topology: str) -> int:
  return 1 if get_topology_product(topology) == 1 else 4


def compute_num_tensorcores(tensorcores_per_chip: int, topology: str) -> int:
  return get_topology_product(topology) * tensorcores_per_chip


def compute_vms_per_slice(topology: str) -> int:
  chips_per_vm = compute_chips_per_vm(topology)
  return get_topology_product(topology) // chips_per_vm


################### Subcommand Helper Functions #############################
""" !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
IF YOU MODIFY THE BELOW UserFacingNameToSystemCharacteristics MAP YOU SHOULD
ALSO ADD CORRESPONDING MODIFICATIONS TO UserFacingNameToSystemCharacteristics
IN MaxText/accelerator_to_spec_map.py !!!!! """
# vvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvv
UserFacingNameToSystemCharacteristics = {
    # GPU system characteristics
    # l4-$CHIPSc
    'l4-1': SystemCharacteristics(
        topology='N/A',
        vms_per_slice=1,
        gke_accelerator='nvidia-l4',
        gce_machine_type='g2-standard-12',
        chips_per_vm=1,
        accelerator_type=AcceleratorType['GPU'],
        device_type='l4-1',
        supports_sub_slicing=False,
    ),
    'l4-2': SystemCharacteristics(
        topology='N/A',
        vms_per_slice=1,
        gke_accelerator='nvidia-l4',
        gce_machine_type='g2-standard-24',
        chips_per_vm=2,
        accelerator_type=AcceleratorType['GPU'],
        device_type='l4-2',
        supports_sub_slicing=False,
    ),
    'l4-4': SystemCharacteristics(
        topology='N/A',
        vms_per_slice=1,
        gke_accelerator='nvidia-l4',
        gce_machine_type='g2-standard-48',
        chips_per_vm=4,
        accelerator_type=AcceleratorType['GPU'],
        device_type='l4-4',
        supports_sub_slicing=False,
    ),
    'l4-8': SystemCharacteristics(
        topology='N/A',
        vms_per_slice=1,
        gke_accelerator='nvidia-l4',
        gce_machine_type='g2-standard-96',
        chips_per_vm=8,
        accelerator_type=AcceleratorType['GPU'],
        device_type='l4-8',
        supports_sub_slicing=False,
    ),
    # A100-40gb-$CHIPSc
    'a100-40gb-1': SystemCharacteristics(
        topology='N/A',
        vms_per_slice=1,
        gke_accelerator='nvidia-tesla-a100',
        gce_machine_type='a2-highgpu-1g',
        chips_per_vm=1,
        accelerator_type=AcceleratorType['GPU'],
        device_type='a100-40gb-1',
        supports_sub_slicing=False,
    ),
    'a100-40gb-2': SystemCharacteristics(
        topology='N/A',
        vms_per_slice=1,
        gke_accelerator='nvidia-tesla-a100',
        gce_machine_type='a2-highgpu-2g',
        chips_per_vm=2,
        accelerator_type=AcceleratorType['GPU'],
        device_type='a100-40gb-2',
        supports_sub_slicing=False,
    ),
    'a100-40gb-4': SystemCharacteristics(
        topology='N/A',
        vms_per_slice=1,
        gke_accelerator='nvidia-tesla-a100',
        gce_machine_type='a2-highgpu-4g',
        chips_per_vm=4,
        accelerator_type=AcceleratorType['GPU'],
        device_type='a100-40gb-4',
        supports_sub_slicing=False,
    ),
    'a100-40gb-8': SystemCharacteristics(
        topology='N/A',
        vms_per_slice=1,
        gke_accelerator='nvidia-tesla-a100',
        gce_machine_type='a2-highgpu-8g',
        chips_per_vm=8,
        accelerator_type=AcceleratorType['GPU'],
        device_type='a100-40gb-8',
        supports_sub_slicing=False,
    ),
    'gb200-4': SystemCharacteristics(
        topology='1x72',
        vms_per_slice=1,
        gke_accelerator='nvidia-gb200',
        gce_machine_type='a4x-highgpu-4g',
        chips_per_vm=4,
        accelerator_type=AcceleratorType['GPU'],
        device_type='gb200-4',
        supports_sub_slicing=False,
    ),
    'gb200-4-nolssd': SystemCharacteristics(
        topology='1x72',
        vms_per_slice=1,
        gke_accelerator='nvidia-gb200',
        gce_machine_type='a4x-highgpu-4g-nolssd',
        chips_per_vm=4,
        accelerator_type=AcceleratorType['GPU'],
        device_type='gb200-4',
        supports_sub_slicing=False,
    ),
    'b200-8': SystemCharacteristics(
        topology='N/A',
        vms_per_slice=1,
        gke_accelerator='nvidia-b200',
        gce_machine_type='a4-highgpu-8g',
        chips_per_vm=8,
        accelerator_type=AcceleratorType['GPU'],
        device_type='b200-8',
        supports_sub_slicing=False,
    ),
    'h200-141gb-8': SystemCharacteristics(
        topology='N/A',
        vms_per_slice=1,
        gke_accelerator='nvidia-h200-141gb',
        gce_machine_type='a3-ultragpu-8g',
        chips_per_vm=8,
        accelerator_type=AcceleratorType['GPU'],
        device_type='h200-141gb-8',
        supports_sub_slicing=False,
    ),
    # H100-80gb-$CHIPS
    'h100-80gb-8': SystemCharacteristics(
        topology='N/A',
        vms_per_slice=1,
        gke_accelerator='nvidia-h100-80gb',
        gce_machine_type='a3-highgpu-8g',
        chips_per_vm=8,
        accelerator_type=AcceleratorType['GPU'],
        device_type='h100-80gb-8',
        supports_sub_slicing=False,
    ),
    # H100-mega-80gb-$CHIPS
    'h100-mega-80gb-8': SystemCharacteristics(
        topology='N/A',
        vms_per_slice=1,
        gke_accelerator='nvidia-h100-mega-80gb',
        gce_machine_type='a3-megagpu-8g',
        chips_per_vm=8,
        accelerator_type=AcceleratorType['GPU'],
        device_type='h100-mega-80gb-8',
        supports_sub_slicing=False,
    ),
    # TPU system characteristics
    **get_tpu_system_characteristics_map(
        prefix='tpu7x',
        tensorcores_per_chip=2,
        gke_accelerator='tpu7x',
        machine_type='tpu7x-standard-1t',
        supported_topologies=['1x1x1'],
        requires_workload_policy=True,
        supports_sub_slicing=False,
    ),
    **get_tpu_system_characteristics_map(
        prefix='tpu7x',
        tensorcores_per_chip=2,
        gke_accelerator='tpu7x',
        machine_type='tpu7x-standard-4t',
        requires_workload_policy=True,
        supports_sub_slicing=False,
        supported_topologies=[
            '12x12x12',
            '12x12x16',
            '12x12x20',
            '12x12x24',
            '12x12x28',
            '12x12x36',
            '12x16x16',
            '12x16x20',
            '12x16x24',
            '12x16x28',
            '12x20x20',
            '12x20x24',
            '12x24x24',
            '16x16x16',
            '16x16x20',
            '16x16x24',
            '16x16x32',
            '16x20x28',
            '16x24x24',
            '2x2x1',
            '2x2x2',
            '2x2x4',
            '2x4x4',
            '4x12x116',
            '4x12x12',
            '4x12x124',
            '4x12x20',
            '4x12x28',
            '4x12x44',
            '4x12x52',
            '4x12x68',
            '4x12x76',
            '4x12x92',
            '4x20x20',
            '4x20x28',
            '4x20x44',
            '4x20x52',
            '4x20x68',
            '4x20x76',
            '4x28x28',
            '4x28x44',
            '4x28x52',
            '4x4x116',
            '4x4x12',
            '4x4x124',
            '4x4x148',
            '4x4x164',
            '4x4x172',
            '4x4x188',
            '4x4x20',
            '4x4x212',
            '4x4x236',
            '4x4x244',
            '4x4x28',
            '4x4x4',
            '4x4x44',
            '4x4x52',
            '4x4x68',
            '4x4x76',
            '4x4x8',
            '4x4x92',
            '4x8x116',
            '4x8x12',
            '4x8x124',
            '4x8x148',
            '4x8x164',
            '4x8x172',
            '4x8x188',
            '4x8x20',
            '4x8x28',
            '4x8x44',
            '4x8x52',
            '4x8x68',
            '4x8x76',
            '4x8x8',
            '4x8x92',
            '8x12x12',
            '8x12x16',
            '8x12x20',
            '8x12x28',
            '8x12x44',
            '8x12x52',
            '8x16x16',
            '8x16x20',
            '8x16x28',
            '8x16x44',
            '8x20x20',
            '8x20x28',
            '8x8x12',
            '8x8x16',
            '8x8x20',
            '8x8x28',
            '8x8x44',
            '8x8x52',
            '8x8x68',
            '8x8x76',
            '8x8x8',
            '8x8x92',
        ],
    ),
    **get_tpu_system_characteristics_map(
        prefix='v6e',
        tensorcores_per_chip=1,
        gke_accelerator='tpu-v6e-slice',
        machine_type='ct6e-standard-1t',
        supports_sub_slicing=False,
        supported_topologies=['1x1'],
    ),
    **get_tpu_system_characteristics_map(
        prefix='v6e',
        tensorcores_per_chip=1,
        gke_accelerator='tpu-v6e-slice',
        machine_type='ct6e-standard-4t',
        supports_sub_slicing=True,
        supported_topologies=[
            '2x2',
            '2x4',
            '4x4',
            '4x8',
            '8x8',
            '8x16',
            '16x16',
        ],
    ),
    **get_tpu_system_characteristics_map(
        prefix='v5p',
        tensorcores_per_chip=2,
        gke_accelerator='tpu-v5p-slice',
        machine_type='ct5p-hightpu-4t',
        supports_sub_slicing=False,
        supported_topologies=[
            '2x2x1',
            '2x2x2',
            '2x2x4',
            '2x4x4',
            '4x4x4',
            '4x4x8',
            '4x4x12',
            '4x8x8',
            '4x4x20',
            '4x8x12',
            '4x4x28',
            '8x8x8',
            '4x12x12',
            '4x8x20',
            '4x4x44',
            '8x8x12',
            '4x4x52',
            '4x8x28',
            '4x12x20',
            '8x8x16',
            '4x4x68',
            '8x12x12',
            '4x4x76',
            '8x8x20',
            '4x12x28',
            '4x8x44',
            '4x4x92',
            '8x12x16',
            '4x20x20',
            '4x8x52',
            '12x12x12',
            '8x8x28',
            '4x4x116',
            '8x12x20',
            '4x4x124',
            '8x16x16',
            '4x12x44',
            '4x8x68',
            '4x20x28',
            '12x12x16',
            '4x4x148',
            '4x8x76',
            '4x12x52',
            '8x16x20',
            '4x4x164',
            '8x12x28',
            '4x4x172',
            '8x8x44',
            '12x12x20',
            '4x8x92',
            '4x4x188',
            '12x16x16',
            '4x28x28',
            '8x20x20',
            '4x12x68',
            '8x8x52',
            '4x4x212',
            '12x12x24',
            '4x20x44',
            '8x16x28',
            '4x12x76',
            '4x8x116',
            '4x4x236',
            '12x16x20',
            '4x4x244',
            '4x8x124',
            '12x12x28',
            '16x16x16',
            '4x20x52',
            '8x12x44',
            '8x8x68',
            '4x12x92',
            '8x20x28',
            '12x16x24',
            '4x8x148',
            '12x20x20',
            '8x8x76',
            '4x28x44',
            '8x12x52',
            '16x16x20',
            '12x12x36',
            '4x8x164',
            '12x16x28',
            '4x20x68',
            '4x8x172',
            '4x12x116',
            '8x16x44',
            '12x20x24',
            '4x28x52',
            '8x8x92',
            '4x12x124',
            '4x8x188',
            '4x20x76',
            '16x16x24',
            '12x24x24',
            '16x20x28',
        ],
    ),
    **get_tpu_system_characteristics_map(
        prefix='v5litepod',
        tensorcores_per_chip=1,
        gke_accelerator='tpu-v5-lite-podslice',
        machine_type='ct5lp-hightpu-4t',
        supports_sub_slicing=False,
        supported_topologies=['2x4', '4x4', '4x8', '8x8', '8x16', '16x16'],
    ),
    **get_tpu_system_characteristics_map(
        prefix='v4',
        tensorcores_per_chip=2,
        gke_accelerator='tpu-v4-podslice',
        machine_type='ct4p-hightpu-4t',
        supports_sub_slicing=False,
        supported_topologies=[
            '2x2x1',
            '2x2x2',
            '2x2x4',
            '2x4x4',
            '4x4x4',
            '4x4x8',
            '4x8x8',
            '8x8x8',
            '8x8x12',
            '8x8x16',
            '8x16x16',
        ],
    ),
    # CPU system characteristics.
    # Note that chips_per_vm is actually the number of vCPUs in that CPU.
    # There are no chips in CPUs.
    # m1-megamem-#vCPUs-#VMs
    'm1-megamem-96-1': SystemCharacteristics(
        topology='N/A',
        vms_per_slice=1,
        gke_accelerator='N/A',
        gce_machine_type='m1-megamem-96',
        chips_per_vm=96,
        accelerator_type=AcceleratorType['CPU'],
        device_type='m1-megamem-96-1',
        supports_sub_slicing=False,
    ),
    # n2-standard-#vCPUs-#VMs
    'n2-standard-64-1': SystemCharacteristics(
        topology='N/A',
        vms_per_slice=1,
        gke_accelerator='N/A',
        gce_machine_type='n2-standard-64',
        chips_per_vm=64,
        accelerator_type=AcceleratorType['CPU'],
        device_type='n2-standard-64-1',
        supports_sub_slicing=False,
    ),
    'n2-standard-32-1': SystemCharacteristics(
        topology='N/A',
        vms_per_slice=1,
        gke_accelerator='N/A',
        gce_machine_type='n2-standard-32',
        chips_per_vm=32,
        accelerator_type=AcceleratorType['CPU'],
        device_type='n2-standard-32-1',
        supports_sub_slicing=False,
    ),
    'n2-standard-32-2': SystemCharacteristics(
        topology='N/A',
        vms_per_slice=2,
        gke_accelerator='N/A',
        gce_machine_type='n2-standard-32',
        chips_per_vm=32,
        accelerator_type=AcceleratorType['CPU'],
        device_type='n2-standard-32-2',
        supports_sub_slicing=False,
    ),
    'n2-standard-32-4': SystemCharacteristics(
        topology='N/A',
        vms_per_slice=4,
        gke_accelerator='N/A',
        gce_machine_type='n2-standard-32',
        chips_per_vm=32,
        accelerator_type=AcceleratorType['CPU'],
        device_type='n2-standard-32-4',
        supports_sub_slicing=False,
    ),
    'n2-standard-32-8': SystemCharacteristics(
        topology='N/A',
        vms_per_slice=8,
        gke_accelerator='N/A',
        gce_machine_type='n2-standard-32',
        chips_per_vm=32,
        accelerator_type=AcceleratorType['CPU'],
        device_type='n2-standard-32-8',
        supports_sub_slicing=False,
    ),
    'n2-standard-32-16': SystemCharacteristics(
        topology='N/A',
        vms_per_slice=16,
        gke_accelerator='N/A',
        gce_machine_type='n2-standard-32',
        chips_per_vm=32,
        accelerator_type=AcceleratorType['CPU'],
        device_type='n2-standard-32-16',
        supports_sub_slicing=False,
    ),
    'n2-standard-32-32': SystemCharacteristics(
        topology='N/A',
        vms_per_slice=32,
        gke_accelerator='N/A',
        gce_machine_type='n2-standard-32',
        chips_per_vm=32,
        accelerator_type=AcceleratorType['CPU'],
        device_type='n2-standard-32-32',
        supports_sub_slicing=False,
    ),
    'n2-standard-32-64': SystemCharacteristics(
        topology='N/A',
        vms_per_slice=64,
        gke_accelerator='N/A',
        gce_machine_type='n2-standard-32',
        chips_per_vm=32,
        accelerator_type=AcceleratorType['CPU'],
        device_type='n2-standard-32-64',
        supports_sub_slicing=False,
    ),
    'n2-standard-32-128': SystemCharacteristics(
        topology='N/A',
        vms_per_slice=128,
        gke_accelerator='N/A',
        gce_machine_type='n2-standard-32',
        chips_per_vm=32,
        accelerator_type=AcceleratorType['CPU'],
        device_type='n2-standard-32-128',
        supports_sub_slicing=False,
    ),
    'n2-standard-32-256': SystemCharacteristics(
        topology='N/A',
        vms_per_slice=256,
        gke_accelerator='N/A',
        gce_machine_type='n2-standard-32',
        chips_per_vm=32,
        accelerator_type=AcceleratorType['CPU'],
        device_type='n2-standard-32-256',
        supports_sub_slicing=False,
    ),
    'n2-standard-32-512': SystemCharacteristics(
        topology='N/A',
        vms_per_slice=512,
        gke_accelerator='N/A',
        gce_machine_type='n2-standard-32',
        chips_per_vm=32,
        accelerator_type=AcceleratorType['CPU'],
        device_type='n2-standard-32-512',
        supports_sub_slicing=False,
    ),
    'n2-standard-32-1024': SystemCharacteristics(
        topology='N/A',
        vms_per_slice=1024,
        gke_accelerator='N/A',
        gce_machine_type='n2-standard-32',
        chips_per_vm=32,
        accelerator_type=AcceleratorType['CPU'],
        device_type='n2-standard-32-1024',
        supports_sub_slicing=False,
    ),
    'n2-standard-32-2048': SystemCharacteristics(
        topology='N/A',
        vms_per_slice=2048,
        gke_accelerator='N/A',
        gce_machine_type='n2-standard-32',
        chips_per_vm=32,
        accelerator_type=AcceleratorType['CPU'],
        device_type='n2-standard-32-2048',
        supports_sub_slicing=False,
    ),
}
""" If you modify UserFacingNameToSystemCharacteristics you should also modify
the corresponding Map in MaxText/accelerator_to_spec_map.py """
