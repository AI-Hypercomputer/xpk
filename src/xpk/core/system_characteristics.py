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
from functools import reduce
from operator import mul

AcceleratorType = {'TPU': 1, 'GPU': 2, 'CPU': 3}


@dataclass
class AcceleratorCharacteristics:
  resource_type: str
  accelerator_label: str
  machine_label: str


AcceleratorTypeToAcceleratorCharacteristics = {
    # TPU
    AcceleratorType['TPU']: AcceleratorCharacteristics(
        'google.com/tpu',
        'cloud.google.com/gke-tpu-accelerator',
        'cloud.google.com/gke-tpu-topology',
    ),
    # GPU
    AcceleratorType['GPU']: AcceleratorCharacteristics(
        'nvidia.com/gpu',
        'cloud.google.com/gke-accelerator',
        'cloud.google.com/gce-machine-type',
    ),
    # CPU
    AcceleratorType['CPU']: AcceleratorCharacteristics(
        'cpu', '', 'cloud.google.com/gke-nodepool'
    ),
}


@dataclass
class SystemCharacteristics:
  topology: str
  vms_per_slice: int
  gke_accelerator: str
  gce_machine_type: str
  chips_per_vm: int
  accelerator_type: int  # TODO: use enums
  device_type: str


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
) -> dict[str, SystemCharacteristics]:
  system_characteristics_map = {}
  for topology in supported_topologies:
    total_chips = reduce(mul, (int(x) for x in topology.split('x')), 1)
    num_tensorcores = total_chips * tensorcores_per_chip
    chips_per_vm = 1 if total_chips == 1 else 4
    vms_per_slice = total_chips // chips_per_vm
    system = SystemCharacteristics(
        topology,
        vms_per_slice,
        gke_accelerator,
        machine_type,
        chips_per_vm,
        AcceleratorType['TPU'],
        f'{prefix}-{num_tensorcores}',
    )
    system_characteristics_map[f'{prefix}-{topology}'] = system
    system_characteristics_map[f'{prefix}-{num_tensorcores}'] = system

  return system_characteristics_map


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
        'N/A',
        1,
        'nvidia-l4',
        'g2-standard-12',
        1,
        AcceleratorType['GPU'],
        'l4-1',
    ),
    'l4-2': SystemCharacteristics(
        'N/A',
        1,
        'nvidia-l4',
        'g2-standard-24',
        2,
        AcceleratorType['GPU'],
        'l4-2',
    ),
    'l4-4': SystemCharacteristics(
        'N/A',
        1,
        'nvidia-l4',
        'g2-standard-48',
        4,
        AcceleratorType['GPU'],
        'l4-4',
    ),
    'l4-8': SystemCharacteristics(
        'N/A',
        1,
        'nvidia-l4',
        'g2-standard-96',
        8,
        AcceleratorType['GPU'],
        'l4-8',
    ),
    # A100-40gb-$CHIPSc
    'a100-40gb-1': SystemCharacteristics(
        'N/A',
        1,
        'nvidia-tesla-a100',
        'a2-highgpu-1g',
        1,
        AcceleratorType['GPU'],
        'a100-40gb-1',
    ),
    'a100-40gb-2': SystemCharacteristics(
        'N/A',
        1,
        'nvidia-tesla-a100',
        'a2-highgpu-2g',
        2,
        AcceleratorType['GPU'],
        'a100-40gb-2',
    ),
    'a100-40gb-4': SystemCharacteristics(
        'N/A',
        1,
        'nvidia-tesla-a100',
        'a2-highgpu-4g',
        4,
        AcceleratorType['GPU'],
        'a100-40gb-4',
    ),
    'a100-40gb-8': SystemCharacteristics(
        'N/A',
        1,
        'nvidia-tesla-a100',
        'a2-highgpu-8g',
        8,
        AcceleratorType['GPU'],
        'a100-40gb-8',
    ),
    'b200-8': SystemCharacteristics(
        'N/A',
        1,
        'nvidia-b200',
        'a4-highgpu-8g',
        8,
        AcceleratorType['GPU'],
        'b200-8',
    ),
    'h200-141gb-8': SystemCharacteristics(
        'N/A',
        1,
        'nvidia-h200-141gb',
        'a3-ultragpu-8g',
        8,
        AcceleratorType['GPU'],
        'h200-141gb-8',
    ),
    # H100-80gb-$CHIPS
    'h100-80gb-8': SystemCharacteristics(
        'N/A',
        1,
        'nvidia-h100-80gb',
        'a3-highgpu-8g',
        8,
        AcceleratorType['GPU'],
        'h100-80gb-8',
    ),
    # H100-mega-80gb-$CHIPS
    'h100-mega-80gb-8': SystemCharacteristics(
        'N/A',
        1,
        'nvidia-h100-mega-80gb',
        'a3-megagpu-8g',
        8,
        AcceleratorType['GPU'],
        'h100-mega-80gb-8',
    ),
    # TPU system characteristics
    **get_tpu_system_characteristics_map(
        'tpu7x', 2, 'tpu7x', 'tpu7x-standard-1t', ['1x1x1']
    ),
    **get_tpu_system_characteristics_map(
        'tpu7x',
        2,
        'tpu7x',
        'tpu7x-standard-4t',
        [
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
        'v6e', 1, 'tpu-v6e-slice', 'ct6e-standard-1t', ['1x1']
    ),
    **get_tpu_system_characteristics_map(
        'v6e',
        1,
        'tpu-v6e-slice',
        'ct6e-standard-4t',
        ['2x2', '2x4', '4x4', '4x8', '8x8', '8x16', '16x16'],
    ),
    **get_tpu_system_characteristics_map(
        'v5p',
        2,
        'tpu-v5p-slice',
        'ct5p-hightpu-4t',
        [
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
        'v5litepod',
        1,
        'tpu-v5-lite-podslice',
        'ct5lp-hightpu-4t',
        ['2x4', '4x4', '4x8', '8x8', '8x16', '16x16'],
    ),
    **get_tpu_system_characteristics_map(
        'v4',
        2,
        'tpu-v4-podslice',
        'ct4p-hightpu-4t',
        [
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
        'N/A',
        1,
        'N/A',
        'm1-megamem-96',
        96,
        AcceleratorType['CPU'],
        'm1-megamem-96-1',
    ),
    # n2-standard-#vCPUs-#VMs
    'n2-standard-64-1': SystemCharacteristics(
        'N/A',
        1,
        'N/A',
        'n2-standard-64',
        64,
        AcceleratorType['CPU'],
        'n2-standard-64-1',
    ),
    'n2-standard-32-1': SystemCharacteristics(
        'N/A',
        1,
        'N/A',
        'n2-standard-32',
        32,
        AcceleratorType['CPU'],
        'n2-standard-32-1',
    ),
    'n2-standard-32-2': SystemCharacteristics(
        'N/A',
        2,
        'N/A',
        'n2-standard-32',
        32,
        AcceleratorType['CPU'],
        'n2-standard-32-2',
    ),
    'n2-standard-32-4': SystemCharacteristics(
        'N/A',
        4,
        'N/A',
        'n2-standard-32',
        32,
        AcceleratorType['CPU'],
        'n2-standard-32-4',
    ),
    'n2-standard-32-8': SystemCharacteristics(
        'N/A',
        8,
        'N/A',
        'n2-standard-32',
        32,
        AcceleratorType['CPU'],
        'n2-standard-32-8',
    ),
    'n2-standard-32-16': SystemCharacteristics(
        'N/A',
        16,
        'N/A',
        'n2-standard-32',
        32,
        AcceleratorType['CPU'],
        'n2-standard-32-16',
    ),
    'n2-standard-32-32': SystemCharacteristics(
        'N/A',
        32,
        'N/A',
        'n2-standard-32',
        32,
        AcceleratorType['CPU'],
        'n2-standard-32-32',
    ),
    'n2-standard-32-64': SystemCharacteristics(
        'N/A',
        64,
        'N/A',
        'n2-standard-32',
        32,
        AcceleratorType['CPU'],
        'n2-standard-32-64',
    ),
    'n2-standard-32-128': SystemCharacteristics(
        'N/A',
        128,
        'N/A',
        'n2-standard-32',
        32,
        AcceleratorType['CPU'],
        'n2-standard-32-128',
    ),
    'n2-standard-32-256': SystemCharacteristics(
        'N/A',
        256,
        'N/A',
        'n2-standard-32',
        32,
        AcceleratorType['CPU'],
        'n2-standard-32-256',
    ),
    'n2-standard-32-512': SystemCharacteristics(
        'N/A',
        512,
        'N/A',
        'n2-standard-32',
        32,
        AcceleratorType['CPU'],
        'n2-standard-32-512',
    ),
    'n2-standard-32-1024': SystemCharacteristics(
        'N/A',
        1024,
        'N/A',
        'n2-standard-32',
        32,
        AcceleratorType['CPU'],
        'n2-standard-32-1024',
    ),
    'n2-standard-32-2048': SystemCharacteristics(
        'N/A',
        2048,
        'N/A',
        'n2-standard-32',
        32,
        AcceleratorType['CPU'],
        'n2-standard-32-2048',
    ),
}
""" If you modify UserFacingNameToSystemCharacteristics you should also modify
the corresponding Map in MaxText/accelerator_to_spec_map.py """
