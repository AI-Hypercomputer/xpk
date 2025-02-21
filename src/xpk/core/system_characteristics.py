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
  accelerator_type: AcceleratorType  # type: ignore
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
    # v6e
    'v6e-1': SystemCharacteristics(
        '1x1',
        1,
        'tpu-v6e-slice',
        'ct6e-standard-1t',
        1,
        AcceleratorType['TPU'],
        'v6e-1',
    ),
    'v6e-4': SystemCharacteristics(
        '2x2',
        1,
        'tpu-v6e-slice',
        'ct6e-standard-4t',
        4,
        AcceleratorType['TPU'],
        'v6e-4',
    ),
    'v6e-8': SystemCharacteristics(
        '2x4',
        2,
        'tpu-v6e-slice',
        'ct6e-standard-4t',
        4,
        AcceleratorType['TPU'],
        'v6e-8',
    ),
    'v6e-16': SystemCharacteristics(
        '4x4',
        4,
        'tpu-v6e-slice',
        'ct6e-standard-4t',
        4,
        AcceleratorType['TPU'],
        'v6e-16',
    ),
    'v6e-32': SystemCharacteristics(
        '4x8',
        8,
        'tpu-v6e-slice',
        'ct6e-standard-4t',
        4,
        AcceleratorType['TPU'],
        'v6e-32',
    ),
    'v6e-64': SystemCharacteristics(
        '8x8',
        16,
        'tpu-v6e-slice',
        'ct6e-standard-4t',
        4,
        AcceleratorType['TPU'],
        'v6e-64',
    ),
    'v6e-128': SystemCharacteristics(
        '8x16',
        32,
        'tpu-v6e-slice',
        'ct6e-standard-4t',
        4,
        AcceleratorType['TPU'],
        'v6e-128',
    ),
    'v6e-256': SystemCharacteristics(
        '16x16',
        64,
        'tpu-v6e-slice',
        'ct6e-standard-4t',
        4,
        AcceleratorType['TPU'],
        'v6e-256',
    ),
    # v5p
    'v5p-8': SystemCharacteristics(
        '2x2x1',
        1,
        'tpu-v5p-slice',
        'ct5p-hightpu-4t',
        4,
        AcceleratorType['TPU'],
        'v5p-8',
    ),
    'v5p-16': SystemCharacteristics(
        '2x2x2',
        2,
        'tpu-v5p-slice',
        'ct5p-hightpu-4t',
        4,
        AcceleratorType['TPU'],
        'v5p-16',
    ),
    'v5p-32': SystemCharacteristics(
        '2x2x4',
        4,
        'tpu-v5p-slice',
        'ct5p-hightpu-4t',
        4,
        AcceleratorType['TPU'],
        'v5p-32',
    ),
    'v5p-64': SystemCharacteristics(
        '2x4x4',
        8,
        'tpu-v5p-slice',
        'ct5p-hightpu-4t',
        4,
        AcceleratorType['TPU'],
        'v5p-64',
    ),
    'v5p-128': SystemCharacteristics(
        '4x4x4',
        16,
        'tpu-v5p-slice',
        'ct5p-hightpu-4t',
        4,
        AcceleratorType['TPU'],
        'v5p-128',
    ),
    'v5p-256': SystemCharacteristics(
        '4x4x8',
        32,
        'tpu-v5p-slice',
        'ct5p-hightpu-4t',
        4,
        AcceleratorType['TPU'],
        'v5p-256',
    ),
    'v5p-384': SystemCharacteristics(
        '4x4x12',
        48,
        'tpu-v5p-slice',
        'ct5p-hightpu-4t',
        4,
        AcceleratorType['TPU'],
        'v5p-384',
    ),
    'v5p-512': SystemCharacteristics(
        '4x8x8',
        64,
        'tpu-v5p-slice',
        'ct5p-hightpu-4t',
        4,
        AcceleratorType['TPU'],
        'v5p-512',
    ),
    'v5p-640': SystemCharacteristics(
        '4x4x20',
        80,
        'tpu-v5p-slice',
        'ct5p-hightpu-4t',
        4,
        AcceleratorType['TPU'],
        'v5p-640',
    ),
    'v5p-768': SystemCharacteristics(
        '4x8x12',
        96,
        'tpu-v5p-slice',
        'ct5p-hightpu-4t',
        4,
        AcceleratorType['TPU'],
        'v5p-768',
    ),
    'v5p-896': SystemCharacteristics(
        '4x4x28',
        112,
        'tpu-v5p-slice',
        'ct5p-hightpu-4t',
        4,
        AcceleratorType['TPU'],
        'v5p-896',
    ),
    'v5p-1024': SystemCharacteristics(
        '8x8x8',
        128,
        'tpu-v5p-slice',
        'ct5p-hightpu-4t',
        4,
        AcceleratorType['TPU'],
        'v5p-1024',
    ),
    'v5p-1152': SystemCharacteristics(
        '4x12x12',
        144,
        'tpu-v5p-slice',
        'ct5p-hightpu-4t',
        4,
        AcceleratorType['TPU'],
        'v5p-1152',
    ),
    'v5p-1280': SystemCharacteristics(
        '4x8x20',
        160,
        'tpu-v5p-slice',
        'ct5p-hightpu-4t',
        4,
        AcceleratorType['TPU'],
        'v5p-1280',
    ),
    'v5p-1408': SystemCharacteristics(
        '4x4x44',
        176,
        'tpu-v5p-slice',
        'ct5p-hightpu-4t',
        4,
        AcceleratorType['TPU'],
        'v5p-1408',
    ),
    'v5p-1536': SystemCharacteristics(
        '8x8x12',
        192,
        'tpu-v5p-slice',
        'ct5p-hightpu-4t',
        4,
        AcceleratorType['TPU'],
        'v5p-1536',
    ),
    'v5p-1664': SystemCharacteristics(
        '4x4x52',
        208,
        'tpu-v5p-slice',
        'ct5p-hightpu-4t',
        4,
        AcceleratorType['TPU'],
        'v5p-1664',
    ),
    'v5p-1792': SystemCharacteristics(
        '4x8x28',
        224,
        'tpu-v5p-slice',
        'ct5p-hightpu-4t',
        4,
        AcceleratorType['TPU'],
        'v5p-1792',
    ),
    'v5p-1920': SystemCharacteristics(
        '4x12x20',
        240,
        'tpu-v5p-slice',
        'ct5p-hightpu-4t',
        4,
        AcceleratorType['TPU'],
        'v5p-1920',
    ),
    'v5p-2048': SystemCharacteristics(
        '8x8x16',
        256,
        'tpu-v5p-slice',
        'ct5p-hightpu-4t',
        4,
        AcceleratorType['TPU'],
        'v5p-2048',
    ),
    'v5p-2176': SystemCharacteristics(
        '4x4x68',
        272,
        'tpu-v5p-slice',
        'ct5p-hightpu-4t',
        4,
        AcceleratorType['TPU'],
        'v5p-2176',
    ),
    'v5p-2304': SystemCharacteristics(
        '8x12x12',
        288,
        'tpu-v5p-slice',
        'ct5p-hightpu-4t',
        4,
        AcceleratorType['TPU'],
        'v5p-2304',
    ),
    'v5p-2432': SystemCharacteristics(
        '4x4x76',
        304,
        'tpu-v5p-slice',
        'ct5p-hightpu-4t',
        4,
        AcceleratorType['TPU'],
        'v5p-2432',
    ),
    'v5p-2560': SystemCharacteristics(
        '8x8x20',
        320,
        'tpu-v5p-slice',
        'ct5p-hightpu-4t',
        4,
        AcceleratorType['TPU'],
        'v5p-2560',
    ),
    'v5p-2688': SystemCharacteristics(
        '4x12x28',
        336,
        'tpu-v5p-slice',
        'ct5p-hightpu-4t',
        4,
        AcceleratorType['TPU'],
        'v5p-2688',
    ),
    'v5p-2816': SystemCharacteristics(
        '4x8x44',
        352,
        'tpu-v5p-slice',
        'ct5p-hightpu-4t',
        4,
        AcceleratorType['TPU'],
        'v5p-2816',
    ),
    'v5p-2944': SystemCharacteristics(
        '4x4x92',
        368,
        'tpu-v5p-slice',
        'ct5p-hightpu-4t',
        4,
        AcceleratorType['TPU'],
        'v5p-2944',
    ),
    'v5p-3072': SystemCharacteristics(
        '8x12x16',
        384,
        'tpu-v5p-slice',
        'ct5p-hightpu-4t',
        4,
        AcceleratorType['TPU'],
        'v5p-3072',
    ),
    'v5p-3200': SystemCharacteristics(
        '4x20x20',
        400,
        'tpu-v5p-slice',
        'ct5p-hightpu-4t',
        4,
        AcceleratorType['TPU'],
        'v5p-3200',
    ),
    'v5p-3328': SystemCharacteristics(
        '4x8x52',
        416,
        'tpu-v5p-slice',
        'ct5p-hightpu-4t',
        4,
        AcceleratorType['TPU'],
        'v5p-3328',
    ),
    'v5p-3456': SystemCharacteristics(
        '12x12x12',
        432,
        'tpu-v5p-slice',
        'ct5p-hightpu-4t',
        4,
        AcceleratorType['TPU'],
        'v5p-3456',
    ),
    'v5p-3584': SystemCharacteristics(
        '8x8x28',
        448,
        'tpu-v5p-slice',
        'ct5p-hightpu-4t',
        4,
        AcceleratorType['TPU'],
        'v5p-3584',
    ),
    'v5p-3712': SystemCharacteristics(
        '4x4x116',
        464,
        'tpu-v5p-slice',
        'ct5p-hightpu-4t',
        4,
        AcceleratorType['TPU'],
        'v5p-3712',
    ),
    'v5p-3840': SystemCharacteristics(
        '8x12x20',
        480,
        'tpu-v5p-slice',
        'ct5p-hightpu-4t',
        4,
        AcceleratorType['TPU'],
        'v5p-3840',
    ),
    'v5p-3968': SystemCharacteristics(
        '4x4x124',
        496,
        'tpu-v5p-slice',
        'ct5p-hightpu-4t',
        4,
        AcceleratorType['TPU'],
        'v5p-3968',
    ),
    'v5p-4096': SystemCharacteristics(
        '8x16x16',
        512,
        'tpu-v5p-slice',
        'ct5p-hightpu-4t',
        4,
        AcceleratorType['TPU'],
        'v5p-4096',
    ),
    'v5p-4224': SystemCharacteristics(
        '4x12x44',
        528,
        'tpu-v5p-slice',
        'ct5p-hightpu-4t',
        4,
        AcceleratorType['TPU'],
        'v5p-4224',
    ),
    'v5p-4352': SystemCharacteristics(
        '4x8x68',
        544,
        'tpu-v5p-slice',
        'ct5p-hightpu-4t',
        4,
        AcceleratorType['TPU'],
        'v5p-4352',
    ),
    'v5p-4480': SystemCharacteristics(
        '4x20x28',
        560,
        'tpu-v5p-slice',
        'ct5p-hightpu-4t',
        4,
        AcceleratorType['TPU'],
        'v5p-4480',
    ),
    'v5p-4608': SystemCharacteristics(
        '12x12x16',
        576,
        'tpu-v5p-slice',
        'ct5p-hightpu-4t',
        4,
        AcceleratorType['TPU'],
        'v5p-4608',
    ),
    'v5p-4736': SystemCharacteristics(
        '4x4x148',
        592,
        'tpu-v5p-slice',
        'ct5p-hightpu-4t',
        4,
        AcceleratorType['TPU'],
        'v5p-4736',
    ),
    'v5p-4864': SystemCharacteristics(
        '4x8x76',
        608,
        'tpu-v5p-slice',
        'ct5p-hightpu-4t',
        4,
        AcceleratorType['TPU'],
        'v5p-4864',
    ),
    'v5p-4992': SystemCharacteristics(
        '4x12x52',
        624,
        'tpu-v5p-slice',
        'ct5p-hightpu-4t',
        4,
        AcceleratorType['TPU'],
        'v5p-4992',
    ),
    'v5p-5120': SystemCharacteristics(
        '8x16x20',
        640,
        'tpu-v5p-slice',
        'ct5p-hightpu-4t',
        4,
        AcceleratorType['TPU'],
        'v5p-5120',
    ),
    'v5p-5248': SystemCharacteristics(
        '4x4x164',
        656,
        'tpu-v5p-slice',
        'ct5p-hightpu-4t',
        4,
        AcceleratorType['TPU'],
        'v5p-5248',
    ),
    'v5p-5376': SystemCharacteristics(
        '8x12x28',
        672,
        'tpu-v5p-slice',
        'ct5p-hightpu-4t',
        4,
        AcceleratorType['TPU'],
        'v5p-5376',
    ),
    'v5p-5504': SystemCharacteristics(
        '4x4x172',
        688,
        'tpu-v5p-slice',
        'ct5p-hightpu-4t',
        4,
        AcceleratorType['TPU'],
        'v5p-5504',
    ),
    'v5p-5632': SystemCharacteristics(
        '8x8x44',
        704,
        'tpu-v5p-slice',
        'ct5p-hightpu-4t',
        4,
        AcceleratorType['TPU'],
        'v5p-5632',
    ),
    'v5p-5760': SystemCharacteristics(
        '12x12x20',
        720,
        'tpu-v5p-slice',
        'ct5p-hightpu-4t',
        4,
        AcceleratorType['TPU'],
        'v5p-5760',
    ),
    'v5p-5888': SystemCharacteristics(
        '4x8x92',
        736,
        'tpu-v5p-slice',
        'ct5p-hightpu-4t',
        4,
        AcceleratorType['TPU'],
        'v5p-5888',
    ),
    'v5p-6016': SystemCharacteristics(
        '4x4x188',
        752,
        'tpu-v5p-slice',
        'ct5p-hightpu-4t',
        4,
        AcceleratorType['TPU'],
        'v5p-6016',
    ),
    'v5p-6144': SystemCharacteristics(
        '12x16x16',
        768,
        'tpu-v5p-slice',
        'ct5p-hightpu-4t',
        4,
        AcceleratorType['TPU'],
        'v5p-6144',
    ),
    'v5p-6272': SystemCharacteristics(
        '4x28x28',
        784,
        'tpu-v5p-slice',
        'ct5p-hightpu-4t',
        4,
        AcceleratorType['TPU'],
        'v5p-6272',
    ),
    'v5p-6400': SystemCharacteristics(
        '8x20x20',
        800,
        'tpu-v5p-slice',
        'ct5p-hightpu-4t',
        4,
        AcceleratorType['TPU'],
        'v5p-6400',
    ),
    'v5p-6528': SystemCharacteristics(
        '4x12x68',
        816,
        'tpu-v5p-slice',
        'ct5p-hightpu-4t',
        4,
        AcceleratorType['TPU'],
        'v5p-6528',
    ),
    'v5p-6656': SystemCharacteristics(
        '8x8x52',
        832,
        'tpu-v5p-slice',
        'ct5p-hightpu-4t',
        4,
        AcceleratorType['TPU'],
        'v5p-6656',
    ),
    'v5p-6784': SystemCharacteristics(
        '4x4x212',
        848,
        'tpu-v5p-slice',
        'ct5p-hightpu-4t',
        4,
        AcceleratorType['TPU'],
        'v5p-6784',
    ),
    'v5p-6912': SystemCharacteristics(
        '12x12x24',
        864,
        'tpu-v5p-slice',
        'ct5p-hightpu-4t',
        4,
        AcceleratorType['TPU'],
        'v5p-6912',
    ),
    'v5p-7040': SystemCharacteristics(
        '4x20x44',
        880,
        'tpu-v5p-slice',
        'ct5p-hightpu-4t',
        4,
        AcceleratorType['TPU'],
        'v5p-7040',
    ),
    'v5p-7168': SystemCharacteristics(
        '8x16x28',
        896,
        'tpu-v5p-slice',
        'ct5p-hightpu-4t',
        4,
        AcceleratorType['TPU'],
        'v5p-7168',
    ),
    'v5p-7296': SystemCharacteristics(
        '4x12x76',
        912,
        'tpu-v5p-slice',
        'ct5p-hightpu-4t',
        4,
        AcceleratorType['TPU'],
        'v5p-7296',
    ),
    'v5p-7424': SystemCharacteristics(
        '4x8x116',
        928,
        'tpu-v5p-slice',
        'ct5p-hightpu-4t',
        4,
        AcceleratorType['TPU'],
        'v5p-7424',
    ),
    'v5p-7552': SystemCharacteristics(
        '4x4x236',
        944,
        'tpu-v5p-slice',
        'ct5p-hightpu-4t',
        4,
        AcceleratorType['TPU'],
        'v5p-7552',
    ),
    'v5p-7680': SystemCharacteristics(
        '12x16x20',
        960,
        'tpu-v5p-slice',
        'ct5p-hightpu-4t',
        4,
        AcceleratorType['TPU'],
        'v5p-7680',
    ),
    'v5p-7808': SystemCharacteristics(
        '4x4x244',
        976,
        'tpu-v5p-slice',
        'ct5p-hightpu-4t',
        4,
        AcceleratorType['TPU'],
        'v5p-7808',
    ),
    'v5p-7936': SystemCharacteristics(
        '4x8x124',
        992,
        'tpu-v5p-slice',
        'ct5p-hightpu-4t',
        4,
        AcceleratorType['TPU'],
        'v5p-7936',
    ),
    'v5p-8064': SystemCharacteristics(
        '12x12x28',
        1008,
        'tpu-v5p-slice',
        'ct5p-hightpu-4t',
        4,
        AcceleratorType['TPU'],
        'v5p-8064',
    ),
    'v5p-8192': SystemCharacteristics(
        '16x16x16',
        1024,
        'tpu-v5p-slice',
        'ct5p-hightpu-4t',
        4,
        AcceleratorType['TPU'],
        'v5p-8192',
    ),
    'v5p-8320': SystemCharacteristics(
        '4x20x52',
        1040,
        'tpu-v5p-slice',
        'ct5p-hightpu-4t',
        4,
        AcceleratorType['TPU'],
        'v5p-8320',
    ),
    'v5p-8448': SystemCharacteristics(
        '8x12x44',
        1056,
        'tpu-v5p-slice',
        'ct5p-hightpu-4t',
        4,
        AcceleratorType['TPU'],
        'v5p-8448',
    ),
    'v5p-8704': SystemCharacteristics(
        '8x8x68',
        1088,
        'tpu-v5p-slice',
        'ct5p-hightpu-4t',
        4,
        AcceleratorType['TPU'],
        'v5p-8704',
    ),
    'v5p-8832': SystemCharacteristics(
        '4x12x92',
        1104,
        'tpu-v5p-slice',
        'ct5p-hightpu-4t',
        4,
        AcceleratorType['TPU'],
        'v5p-8832',
    ),
    'v5p-8960': SystemCharacteristics(
        '8x20x28',
        1120,
        'tpu-v5p-slice',
        'ct5p-hightpu-4t',
        4,
        AcceleratorType['TPU'],
        'v5p-8960',
    ),
    'v5p-9216': SystemCharacteristics(
        '12x16x24',
        1152,
        'tpu-v5p-slice',
        'ct5p-hightpu-4t',
        4,
        AcceleratorType['TPU'],
        'v5p-9216',
    ),
    'v5p-9472': SystemCharacteristics(
        '4x8x148',
        1184,
        'tpu-v5p-slice',
        'ct5p-hightpu-4t',
        4,
        AcceleratorType['TPU'],
        'v5p-9472',
    ),
    'v5p-9600': SystemCharacteristics(
        '12x20x20',
        1200,
        'tpu-v5p-slice',
        'ct5p-hightpu-4t',
        4,
        AcceleratorType['TPU'],
        'v5p-9600',
    ),
    'v5p-9728': SystemCharacteristics(
        '8x8x76',
        1216,
        'tpu-v5p-slice',
        'ct5p-hightpu-4t',
        4,
        AcceleratorType['TPU'],
        'v5p-9728',
    ),
    'v5p-9856': SystemCharacteristics(
        '4x28x44',
        1232,
        'tpu-v5p-slice',
        'ct5p-hightpu-4t',
        4,
        AcceleratorType['TPU'],
        'v5p-9856',
    ),
    'v5p-9984': SystemCharacteristics(
        '8x12x52',
        1248,
        'tpu-v5p-slice',
        'ct5p-hightpu-4t',
        4,
        AcceleratorType['TPU'],
        'v5p-9984',
    ),
    'v5p-10240': SystemCharacteristics(
        '16x16x20',
        1280,
        'tpu-v5p-slice',
        'ct5p-hightpu-4t',
        4,
        AcceleratorType['TPU'],
        'v5p-10240',
    ),
    'v5p-10368': SystemCharacteristics(
        '12x12x36',
        1296,
        'tpu-v5p-slice',
        'ct5p-hightpu-4t',
        4,
        AcceleratorType['TPU'],
        'v5p-10368',
    ),
    'v5p-10496': SystemCharacteristics(
        '4x8x164',
        1312,
        'tpu-v5p-slice',
        'ct5p-hightpu-4t',
        4,
        AcceleratorType['TPU'],
        'v5p-10496',
    ),
    'v5p-10752': SystemCharacteristics(
        '12x16x28',
        1344,
        'tpu-v5p-slice',
        'ct5p-hightpu-4t',
        4,
        AcceleratorType['TPU'],
        'v5p-10752',
    ),
    'v5p-10880': SystemCharacteristics(
        '4x20x68',
        1360,
        'tpu-v5p-slice',
        'ct5p-hightpu-4t',
        4,
        AcceleratorType['TPU'],
        'v5p-10880',
    ),
    'v5p-11008': SystemCharacteristics(
        '4x8x172',
        1376,
        'tpu-v5p-slice',
        'ct5p-hightpu-4t',
        4,
        AcceleratorType['TPU'],
        'v5p-11008',
    ),
    'v5p-11136': SystemCharacteristics(
        '4x12x116',
        1392,
        'tpu-v5p-slice',
        'ct5p-hightpu-4t',
        4,
        AcceleratorType['TPU'],
        'v5p-11136',
    ),
    'v5p-11264': SystemCharacteristics(
        '8x16x44',
        1408,
        'tpu-v5p-slice',
        'ct5p-hightpu-4t',
        4,
        AcceleratorType['TPU'],
        'v5p-11264',
    ),
    'v5p-11520': SystemCharacteristics(
        '12x20x24',
        1440,
        'tpu-v5p-slice',
        'ct5p-hightpu-4t',
        4,
        AcceleratorType['TPU'],
        'v5p-11520',
    ),
    'v5p-11648': SystemCharacteristics(
        '4x28x52',
        1456,
        'tpu-v5p-slice',
        'ct5p-hightpu-4t',
        4,
        AcceleratorType['TPU'],
        'v5p-11648',
    ),
    'v5p-11776': SystemCharacteristics(
        '8x8x92',
        1472,
        'tpu-v5p-slice',
        'ct5p-hightpu-4t',
        4,
        AcceleratorType['TPU'],
        'v5p-11776',
    ),
    'v5p-11904': SystemCharacteristics(
        '4x12x124',
        1488,
        'tpu-v5p-slice',
        'ct5p-hightpu-4t',
        4,
        AcceleratorType['TPU'],
        'v5p-11904',
    ),
    'v5p-12032': SystemCharacteristics(
        '4x8x188',
        1504,
        'tpu-v5p-slice',
        'ct5p-hightpu-4t',
        4,
        AcceleratorType['TPU'],
        'v5p-12032',
    ),
    'v5p-12160': SystemCharacteristics(
        '4x20x76',
        1520,
        'tpu-v5p-slice',
        'ct5p-hightpu-4t',
        4,
        AcceleratorType['TPU'],
        'v5p-12160',
    ),
    'v5p-12288': SystemCharacteristics(
        '16x16x24',
        1536,
        'tpu-v5p-slice',
        'ct5p-hightpu-4t',
        4,
        AcceleratorType['TPU'],
        'v5p-12288',
    ),
    'v5p-13824': SystemCharacteristics(
        '12x24x24',
        1728,
        'tpu-v5p-slice',
        'ct5p-hightpu-4t',
        4,
        AcceleratorType['TPU'],
        'v5p-13824',
    ),
    'v5p-17920': SystemCharacteristics(
        '16x20x28',
        2240,
        'tpu-v5p-slice',
        'ct5p-hightpu-4t',
        4,
        AcceleratorType['TPU'],
        'v5p-17920',
    ),
    # v5litepod
    'v5litepod-8': SystemCharacteristics(
        '2x4',
        2,
        'tpu-v5-lite-podslice',
        'ct5lp-hightpu-4t',
        8,
        AcceleratorType['TPU'],
        'v5litepod-8',
    ),
    'v5litepod-16': SystemCharacteristics(
        '4x4',
        4,
        'tpu-v5-lite-podslice',
        'ct5lp-hightpu-4t',
        4,
        AcceleratorType['TPU'],
        'v5litepod-16',
    ),
    'v5litepod-32': SystemCharacteristics(
        '4x8',
        8,
        'tpu-v5-lite-podslice',
        'ct5lp-hightpu-4t',
        4,
        AcceleratorType['TPU'],
        'v5litepod-32',
    ),
    'v5litepod-64': SystemCharacteristics(
        '8x8',
        16,
        'tpu-v5-lite-podslice',
        'ct5lp-hightpu-4t',
        4,
        AcceleratorType['TPU'],
        'v5litepod-64',
    ),
    'v5litepod-128': SystemCharacteristics(
        '8x16',
        32,
        'tpu-v5-lite-podslice',
        'ct5lp-hightpu-4t',
        4,
        AcceleratorType['TPU'],
        'v5litepod-128',
    ),
    'v5litepod-256': SystemCharacteristics(
        '16x16',
        64,
        'tpu-v5-lite-podslice',
        'ct5lp-hightpu-4t',
        4,
        AcceleratorType['TPU'],
        'v5litepod-256',
    ),
    # v4
    'v4-8': SystemCharacteristics(
        '2x2x1',
        1,
        'tpu-v4-podslice',
        'ct4p-hightpu-4t',
        4,
        AcceleratorType['TPU'],
        'v4-8',
    ),
    'v4-16': SystemCharacteristics(
        '2x2x2',
        2,
        'tpu-v4-podslice',
        'ct4p-hightpu-4t',
        4,
        AcceleratorType['TPU'],
        'v4-16',
    ),
    'v4-32': SystemCharacteristics(
        '2x2x4',
        4,
        'tpu-v4-podslice',
        'ct4p-hightpu-4t',
        4,
        AcceleratorType['TPU'],
        'v4-32',
    ),
    'v4-64': SystemCharacteristics(
        '2x4x4',
        8,
        'tpu-v4-podslice',
        'ct4p-hightpu-4t',
        4,
        AcceleratorType['TPU'],
        'v4-64',
    ),
    'v4-128': SystemCharacteristics(
        '4x4x4',
        16,
        'tpu-v4-podslice',
        'ct4p-hightpu-4t',
        4,
        AcceleratorType['TPU'],
        'v4-128',
    ),
    'v4-256': SystemCharacteristics(
        '4x4x8',
        32,
        'tpu-v4-podslice',
        'ct4p-hightpu-4t',
        4,
        AcceleratorType['TPU'],
        'v4-256',
    ),
    'v4-512': SystemCharacteristics(
        '4x8x8',
        64,
        'tpu-v4-podslice',
        'ct4p-hightpu-4t',
        4,
        AcceleratorType['TPU'],
        'v4-512',
    ),
    'v4-1024': SystemCharacteristics(
        '8x8x8',
        128,
        'tpu-v4-podslice',
        'ct4p-hightpu-4t',
        4,
        AcceleratorType['TPU'],
        'v4-1024',
    ),
    'v4-1536': SystemCharacteristics(
        '8x8x12',
        192,
        'tpu-v4-podslice',
        'ct4p-hightpu-4t',
        4,
        AcceleratorType['TPU'],
        'v4-1536',
    ),
    'v4-2048': SystemCharacteristics(
        '8x8x16',
        256,
        'tpu-v4-podslice',
        'ct4p-hightpu-4t',
        4,
        AcceleratorType['TPU'],
        'v4-2048',
    ),
    'v4-4096': SystemCharacteristics(
        '8x16x16',
        512,
        'tpu-v4-podslice',
        'ct4p-hightpu-4t',
        4,
        AcceleratorType['TPU'],
        'v4-4096',
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
