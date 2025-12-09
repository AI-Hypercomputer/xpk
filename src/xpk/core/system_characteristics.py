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
import dataclasses
from typing import Callable, Literal, Optional

from ..core.workload_decorators import rdma_decorator, tcpxo_decorator, tcpx_decorator
from ..utils.topology import get_topology_product
from enum import Enum

SUB_SLICING_TOPOLOGIES = ['2x4', '4x4', '4x8', '8x8', '8x16', '16x16']

INSTALLER_NCCL_TCPX = 'https://raw.githubusercontent.com/GoogleCloudPlatform/container-engine-accelerators/master/gpudirect-tcpx/nccl-tcpx-installer.yaml'
INSTALLER_NCCL_TCPXO = 'https://raw.githubusercontent.com/GoogleCloudPlatform/container-engine-accelerators/master/gpudirect-tcpxo/nccl-tcpxo-installer.yaml'
INSTALLER_NCCL_RDMA = 'https://raw.githubusercontent.com/GoogleCloudPlatform/container-engine-accelerators/master/gpudirect-rdma/nccl-rdma-installer.yaml'
INSTALLER_NCCL_RDMA_A4X = 'https://raw.githubusercontent.com/GoogleCloudPlatform/container-engine-accelerators/master/gpudirect-rdma/nccl-rdma-installer-a4x.yaml'


class DockerPlatform(str, Enum):
  AMD = 'linux/amd64'
  ARM = 'linux/arm64'


AMD_PLATFORM = DockerPlatform.AMD
ARM_PLATFORM = DockerPlatform.ARM


class AcceleratorType(Enum):
  TPU = 1
  GPU = 2
  CPU = 3

  def __repr__(self):
    return self._name_


@dataclass
class AcceleratorCharacteristics:
  resource_type: str
  accelerator_label: str
  machine_label: str


AcceleratorTypeToAcceleratorCharacteristics = {
    AcceleratorType.TPU: AcceleratorCharacteristics(
        resource_type='google.com/tpu',
        accelerator_label='cloud.google.com/gke-tpu-accelerator',
        machine_label='cloud.google.com/gke-tpu-topology',
    ),
    AcceleratorType.GPU: AcceleratorCharacteristics(
        resource_type='nvidia.com/gpu',
        accelerator_label='cloud.google.com/gke-accelerator',
        machine_label='cloud.google.com/gce-machine-type',
    ),
    AcceleratorType.CPU: AcceleratorCharacteristics(
        resource_type='cpu',
        accelerator_label='',
        machine_label='cloud.google.com/gke-nodepool',
    ),
}


@dataclass
class GpuConfig:
  """Contains GPU-specific configuration and requirements."""

  requires_topology: bool
  gpu_direct_name: Literal['fastrak', 'rdma', 'tcpx', 'tcpxo'] = 'fastrak'
  kjob_decorator_fn: Optional[Callable[[dict], dict]] = None
  """A function to decorate the kjob template for GPU-specific configurations.

  Args:
    job_manifest (dict): The kjob manifest as a dictionary.

  Returns:
    dict: The modified kjob manifest as a dictionary.
  """
  nccl_installer: Optional[str] = None
  jobset_decorator_fn: Optional[Callable[[str, list[str]], str]] = None
  """A function to decorate the jobset for GPU-specific configurations.

  Args:
    jobset_manifest_str (str): The JobSet manifest as a YAML string.
    sub_networks (list[str], optional): A list of sub-network names, used by some decorators.

  Returns:
    str: The modified JobSet manifest as a YAML string.
  """

  def __repr__(self) -> str:
    """Returns a string representation of the GpuConfig, omitting memory addresses for functions."""
    parts = []
    for f in dataclasses.fields(self):
      value = getattr(self, f.name)
      if f.name in ('kjob_decorator_fn', 'jobset_decorator_fn') and value:
        parts.append(f'{f.name}=<function {value.__name__}>')
      else:
        parts.append(f'{f.name}={repr(value)}')
    return f"GpuConfig({', '.join(parts)})"


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
    supports_super_slicing: Whether the Super-slicing feature is supported.
    requires_workload_policy: A boolean indicating if a GCE resource
      workload policy is required. This is automatically set to True for GPUs.
    parallel_containers: The number of containers running on a single VM.

  """

  topology: str
  vms_per_slice: int
  gke_accelerator: str
  gce_machine_type: str
  chips_per_vm: int
  accelerator_type: AcceleratorType
  device_type: str
  supports_sub_slicing: bool
  supports_super_slicing: bool
  supports_accelerator_network_profile: bool
  docker_platform: DockerPlatform
  requires_workload_policy: bool = False
  gpu_config: Optional[GpuConfig] = None
  parallel_containers: int = 1

  def __post_init__(self):
    if self.accelerator_type == AcceleratorType.GPU:
      self.requires_workload_policy = True

      if self.gpu_config is None:
        raise ValueError(
            f"Validation Error: System '{self.device_type}' is a GPU, "
            "but 'gpu_config' was not provided."
        )

  @property
  def gpu_requires_topology(self) -> bool:
    """
    Safely returns whether the GPU config requires topology,
    defaulting to False if no GPU config exists.
    """
    return self.gpu_config.requires_topology if self.gpu_config else False


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


def generate_tpu_topologies(
    max_cubes: int, enforce_nondecreasing: bool = True
) -> list[str]:
  """Generates a list of unique TPU topologies formatted as strings "AxBxC".

  The list will contain all triplets (A, B, C) such that:
    - A, B and C are integers in range 4..256 (including 4 and 256)
    - A, B and C are divisible by 4
    - (A/4) * (B/4) * (C/4) <= max_cubes
    - if enforce_nondecreasing: A <= B <= C
  Additionally, the list will also contain the following triplets:
    2x2x1, 2x2x2, 2x2x4, 2x4x4

  Args:
    max_cubes: maximum number of cubes supported by a TPU platform
    enforce_nondecreasing: whether to enforce A <= B <= C or not
  """
  topologies = ['2x2x1', '2x2x2', '2x2x4', '2x4x4']
  MAX = 256
  for x in range(4, MAX + 1, 4):
    for y in range(x if enforce_nondecreasing else 4, MAX + 1, 4):
      for z in range(y if enforce_nondecreasing else 4, MAX + 1, 4):
        if (x // 4) * (y // 4) * (z // 4) <= max_cubes:
          topologies.append(f'{x}x{y}x{z}')
  return topologies


def get_tpu_system_characteristics_map(
    prefix: str,
    tensorcores_per_chip: int,
    gke_accelerator: str,
    machine_type: str,
    supported_topologies: list[str],
    docker_platform: DockerPlatform,
    supports_accelerator_network_profile: bool,
    tpu_type_requires_workload_policy: bool = False,
    default_topologies: set[str] | None = None,
    sub_slicing_topologies: set[str] | None = None,
    super_slicing_topologies: set[str] | None = None,
    parallel_containers: int = 1,
) -> dict[str, SystemCharacteristics]:
  system_characteristics_map = {}
  default_topologies = default_topologies or set()
  sub_slicing_topologies = sub_slicing_topologies or set()
  super_slicing_topologies = super_slicing_topologies or set()
  for topology in supported_topologies:
    chips_per_vm = compute_chips_per_vm(topology)
    vms_per_slice = compute_vms_per_slice(topology)
    num_tensorcores = compute_num_tensorcores(tensorcores_per_chip, topology)
    device_type = f'{prefix}-{num_tensorcores}'
    system = SystemCharacteristics(
        topology=topology,
        vms_per_slice=vms_per_slice,
        gke_accelerator=gke_accelerator,
        gce_machine_type=machine_type,
        chips_per_vm=chips_per_vm,
        accelerator_type=AcceleratorType.TPU,
        device_type=device_type,
        requires_workload_policy=tpu_type_requires_workload_policy
        and vms_per_slice > 1,
        supports_sub_slicing=topology in sub_slicing_topologies,
        supports_super_slicing=topology in super_slicing_topologies,
        supports_accelerator_network_profile=supports_accelerator_network_profile,
        docker_platform=docker_platform,
        parallel_containers=parallel_containers,
    )
    system_characteristics_map[f'{prefix}-{topology}'] = system
    if (
        topology in default_topologies
        or device_type not in system_characteristics_map
    ):
      system_characteristics_map[device_type] = system

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
        accelerator_type=AcceleratorType.GPU,
        device_type='l4-1',
        supports_sub_slicing=False,
        supports_super_slicing=False,
        supports_accelerator_network_profile=False,
        gpu_config=GpuConfig(requires_topology=False),
        docker_platform=AMD_PLATFORM,
    ),
    'l4-2': SystemCharacteristics(
        topology='N/A',
        vms_per_slice=1,
        gke_accelerator='nvidia-l4',
        gce_machine_type='g2-standard-24',
        chips_per_vm=2,
        accelerator_type=AcceleratorType.GPU,
        device_type='l4-2',
        supports_sub_slicing=False,
        supports_super_slicing=False,
        supports_accelerator_network_profile=False,
        gpu_config=GpuConfig(requires_topology=False),
        docker_platform=AMD_PLATFORM,
    ),
    'l4-4': SystemCharacteristics(
        topology='N/A',
        vms_per_slice=1,
        gke_accelerator='nvidia-l4',
        gce_machine_type='g2-standard-48',
        chips_per_vm=4,
        accelerator_type=AcceleratorType.GPU,
        device_type='l4-4',
        supports_sub_slicing=False,
        supports_super_slicing=False,
        supports_accelerator_network_profile=False,
        gpu_config=GpuConfig(requires_topology=False),
        docker_platform=AMD_PLATFORM,
    ),
    'l4-8': SystemCharacteristics(
        topology='N/A',
        vms_per_slice=1,
        gke_accelerator='nvidia-l4',
        gce_machine_type='g2-standard-96',
        chips_per_vm=8,
        accelerator_type=AcceleratorType.GPU,
        device_type='l4-8',
        supports_sub_slicing=False,
        supports_super_slicing=False,
        supports_accelerator_network_profile=False,
        gpu_config=GpuConfig(requires_topology=False),
        docker_platform=AMD_PLATFORM,
    ),
    # A100-40gb-$CHIPSc
    'a100-40gb-1': SystemCharacteristics(
        topology='N/A',
        vms_per_slice=1,
        gke_accelerator='nvidia-tesla-a100',
        gce_machine_type='a2-highgpu-1g',
        chips_per_vm=1,
        accelerator_type=AcceleratorType.GPU,
        device_type='a100-40gb-1',
        supports_sub_slicing=False,
        supports_super_slicing=False,
        supports_accelerator_network_profile=False,
        gpu_config=GpuConfig(requires_topology=False),
        docker_platform=AMD_PLATFORM,
    ),
    'a100-40gb-2': SystemCharacteristics(
        topology='N/A',
        vms_per_slice=1,
        gke_accelerator='nvidia-tesla-a100',
        gce_machine_type='a2-highgpu-2g',
        chips_per_vm=2,
        accelerator_type=AcceleratorType.GPU,
        device_type='a100-40gb-2',
        supports_sub_slicing=False,
        supports_super_slicing=False,
        supports_accelerator_network_profile=False,
        gpu_config=GpuConfig(requires_topology=False),
        docker_platform=AMD_PLATFORM,
    ),
    'a100-40gb-4': SystemCharacteristics(
        topology='N/A',
        vms_per_slice=1,
        gke_accelerator='nvidia-tesla-a100',
        gce_machine_type='a2-highgpu-4g',
        chips_per_vm=4,
        accelerator_type=AcceleratorType.GPU,
        device_type='a100-40gb-4',
        supports_sub_slicing=False,
        supports_super_slicing=False,
        supports_accelerator_network_profile=False,
        gpu_config=GpuConfig(requires_topology=False),
        docker_platform=AMD_PLATFORM,
    ),
    'a100-40gb-8': SystemCharacteristics(
        topology='N/A',
        vms_per_slice=1,
        gke_accelerator='nvidia-tesla-a100',
        gce_machine_type='a2-highgpu-8g',
        chips_per_vm=8,
        accelerator_type=AcceleratorType.GPU,
        device_type='a100-40gb-8',
        supports_sub_slicing=False,
        supports_super_slicing=False,
        supports_accelerator_network_profile=False,
        gpu_config=GpuConfig(requires_topology=False),
        docker_platform=AMD_PLATFORM,
    ),
    'gb200-4': SystemCharacteristics(
        topology='1x72',
        vms_per_slice=1,
        gke_accelerator='nvidia-gb200',
        gce_machine_type='a4x-highgpu-4g',
        chips_per_vm=4,
        accelerator_type=AcceleratorType.GPU,
        device_type='gb200-4',
        supports_sub_slicing=False,
        supports_super_slicing=False,
        supports_accelerator_network_profile=True,
        gpu_config=GpuConfig(
            requires_topology=True,
            nccl_installer=INSTALLER_NCCL_RDMA_A4X,
            kjob_decorator_fn=rdma_decorator.decorate_kjob_template,
            jobset_decorator_fn=rdma_decorator.decorate_jobset,
            gpu_direct_name='rdma',
        ),
        docker_platform=ARM_PLATFORM,
    ),
    'gb200-4-nolssd': SystemCharacteristics(
        topology='1x72',
        vms_per_slice=1,
        gke_accelerator='nvidia-gb200',
        gce_machine_type='a4x-highgpu-4g-nolssd',
        chips_per_vm=4,
        accelerator_type=AcceleratorType.GPU,
        device_type='gb200-4',
        supports_sub_slicing=False,
        supports_super_slicing=False,
        supports_accelerator_network_profile=True,
        gpu_config=GpuConfig(
            requires_topology=True,
            nccl_installer=INSTALLER_NCCL_RDMA_A4X,
            kjob_decorator_fn=rdma_decorator.decorate_kjob_template,
            jobset_decorator_fn=rdma_decorator.decorate_jobset,
            gpu_direct_name='rdma',
        ),
        docker_platform=ARM_PLATFORM,
    ),
    'b200-8': SystemCharacteristics(
        topology='N/A',
        vms_per_slice=1,
        gke_accelerator='nvidia-b200',
        gce_machine_type='a4-highgpu-8g',
        chips_per_vm=8,
        accelerator_type=AcceleratorType.GPU,
        device_type='b200-8',
        supports_sub_slicing=False,
        supports_super_slicing=False,
        supports_accelerator_network_profile=True,
        gpu_config=GpuConfig(
            requires_topology=True,
            nccl_installer=INSTALLER_NCCL_RDMA,
            kjob_decorator_fn=rdma_decorator.decorate_kjob_template,
            jobset_decorator_fn=rdma_decorator.decorate_jobset,
            gpu_direct_name='rdma',
        ),
        docker_platform=AMD_PLATFORM,
    ),
    'h200-141gb-8': SystemCharacteristics(
        topology='N/A',
        vms_per_slice=1,
        gke_accelerator='nvidia-h200-141gb',
        gce_machine_type='a3-ultragpu-8g',
        chips_per_vm=8,
        accelerator_type=AcceleratorType.GPU,
        device_type='h200-141gb-8',
        supports_sub_slicing=False,
        supports_super_slicing=False,
        supports_accelerator_network_profile=True,
        gpu_config=GpuConfig(
            requires_topology=True,
            nccl_installer=INSTALLER_NCCL_RDMA,
            kjob_decorator_fn=rdma_decorator.decorate_kjob_template,
            jobset_decorator_fn=rdma_decorator.decorate_jobset,
            gpu_direct_name='rdma',
        ),
        docker_platform=AMD_PLATFORM,
    ),
    # H100-80gb-$CHIPS
    'h100-80gb-8': SystemCharacteristics(
        topology='N/A',
        vms_per_slice=1,
        gke_accelerator='nvidia-h100-80gb',
        gce_machine_type='a3-highgpu-8g',
        chips_per_vm=8,
        accelerator_type=AcceleratorType.GPU,
        device_type='h100-80gb-8',
        supports_sub_slicing=False,
        supports_super_slicing=False,
        supports_accelerator_network_profile=True,
        gpu_config=GpuConfig(
            requires_topology=True,
            nccl_installer=INSTALLER_NCCL_TCPX,
            kjob_decorator_fn=tcpx_decorator.decorate_kjob_template,
            jobset_decorator_fn=tcpx_decorator.decorate_jobset,
            gpu_direct_name='tcpx',
        ),
        docker_platform=AMD_PLATFORM,
    ),
    # H100-mega-80gb-$CHIPS
    'h100-mega-80gb-8': SystemCharacteristics(
        topology='N/A',
        vms_per_slice=1,
        gke_accelerator='nvidia-h100-mega-80gb',
        gce_machine_type='a3-megagpu-8g',
        chips_per_vm=8,
        accelerator_type=AcceleratorType.GPU,
        device_type='h100-mega-80gb-8',
        supports_sub_slicing=False,
        supports_super_slicing=False,
        supports_accelerator_network_profile=True,
        gpu_config=GpuConfig(
            requires_topology=True,
            nccl_installer=INSTALLER_NCCL_TCPXO,
            kjob_decorator_fn=tcpxo_decorator.decorate_kjob_template,
            jobset_decorator_fn=tcpxo_decorator.decorate_jobset,
            gpu_direct_name='tcpxo',
        ),
        docker_platform=AMD_PLATFORM,
    ),
    # TPU system characteristics
    **get_tpu_system_characteristics_map(
        prefix='tpu7x',
        tensorcores_per_chip=2,
        gke_accelerator='tpu7x',
        machine_type='tpu7x-standard-1t',
        supported_topologies=['1x1x1'],
        tpu_type_requires_workload_policy=True,
        supports_accelerator_network_profile=False,
        docker_platform=AMD_PLATFORM,
    ),
    **get_tpu_system_characteristics_map(
        prefix='tpu7x',
        tensorcores_per_chip=2,
        gke_accelerator='tpu7x',
        machine_type='tpu7x-standard-4t',
        tpu_type_requires_workload_policy=True,
        supports_accelerator_network_profile=False,
        docker_platform=AMD_PLATFORM,
        parallel_containers=2,
        supported_topologies=generate_tpu_topologies(max_cubes=144),
        super_slicing_topologies=set(['4x4x4']),
        default_topologies=set([
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
        ]),
    ),
    **get_tpu_system_characteristics_map(
        prefix='v6e',
        tensorcores_per_chip=1,
        gke_accelerator='tpu-v6e-slice',
        machine_type='ct6e-standard-1t',
        supported_topologies=['1x1'],
        docker_platform=AMD_PLATFORM,
        supports_accelerator_network_profile=True,
    ),
    **get_tpu_system_characteristics_map(
        prefix='v6e',
        tensorcores_per_chip=1,
        gke_accelerator='tpu-v6e-slice',
        machine_type='ct6e-standard-4t',
        supported_topologies=['2x2'] + SUB_SLICING_TOPOLOGIES,
        sub_slicing_topologies=set(SUB_SLICING_TOPOLOGIES),
        docker_platform=AMD_PLATFORM,
        supports_accelerator_network_profile=True,
    ),
    **get_tpu_system_characteristics_map(
        prefix='v5p',
        tensorcores_per_chip=2,
        gke_accelerator='tpu-v5p-slice',
        machine_type='ct5p-hightpu-4t',
        docker_platform=AMD_PLATFORM,
        supported_topologies=generate_tpu_topologies(max_cubes=140),
        supports_accelerator_network_profile=False,
        default_topologies=set([
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
        ]),
    ),
    **get_tpu_system_characteristics_map(
        prefix='v5litepod',
        tensorcores_per_chip=1,
        gke_accelerator='tpu-v5-lite-podslice',
        machine_type='ct5lp-hightpu-4t',
        docker_platform=AMD_PLATFORM,
        supported_topologies=['2x4', '4x4', '4x8', '8x8', '8x16', '16x16'],
        supports_accelerator_network_profile=False,
    ),
    **get_tpu_system_characteristics_map(
        prefix='v4',
        tensorcores_per_chip=2,
        gke_accelerator='tpu-v4-podslice',
        machine_type='ct4p-hightpu-4t',
        docker_platform=AMD_PLATFORM,
        supported_topologies=generate_tpu_topologies(
            max_cubes=64, enforce_nondecreasing=False
        ),
        supports_accelerator_network_profile=False,
        default_topologies=set([
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
        ]),
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
        accelerator_type=AcceleratorType.CPU,
        device_type='m1-megamem-96-1',
        supports_sub_slicing=False,
        supports_super_slicing=False,
        supports_accelerator_network_profile=False,
        docker_platform=AMD_PLATFORM,
    ),
    # n2-standard-#vCPUs-#VMs
    'n2-standard-64-1': SystemCharacteristics(
        topology='N/A',
        vms_per_slice=1,
        gke_accelerator='N/A',
        gce_machine_type='n2-standard-64',
        chips_per_vm=64,
        accelerator_type=AcceleratorType.CPU,
        device_type='n2-standard-64-1',
        supports_sub_slicing=False,
        supports_super_slicing=False,
        supports_accelerator_network_profile=False,
        docker_platform=AMD_PLATFORM,
    ),
    'n2-standard-32-1': SystemCharacteristics(
        topology='N/A',
        vms_per_slice=1,
        gke_accelerator='N/A',
        gce_machine_type='n2-standard-32',
        chips_per_vm=32,
        accelerator_type=AcceleratorType.CPU,
        device_type='n2-standard-32-1',
        supports_sub_slicing=False,
        supports_super_slicing=False,
        supports_accelerator_network_profile=False,
        docker_platform=AMD_PLATFORM,
    ),
    'n2-standard-32-2': SystemCharacteristics(
        topology='N/A',
        vms_per_slice=2,
        gke_accelerator='N/A',
        gce_machine_type='n2-standard-32',
        chips_per_vm=32,
        accelerator_type=AcceleratorType.CPU,
        device_type='n2-standard-32-2',
        supports_sub_slicing=False,
        supports_super_slicing=False,
        supports_accelerator_network_profile=False,
        docker_platform=AMD_PLATFORM,
    ),
    'n2-standard-32-4': SystemCharacteristics(
        topology='N/A',
        vms_per_slice=4,
        gke_accelerator='N/A',
        gce_machine_type='n2-standard-32',
        chips_per_vm=32,
        accelerator_type=AcceleratorType.CPU,
        device_type='n2-standard-32-4',
        supports_sub_slicing=False,
        supports_super_slicing=False,
        supports_accelerator_network_profile=False,
        docker_platform=AMD_PLATFORM,
    ),
    'n2-standard-32-8': SystemCharacteristics(
        topology='N/A',
        vms_per_slice=8,
        gke_accelerator='N/A',
        gce_machine_type='n2-standard-32',
        chips_per_vm=32,
        accelerator_type=AcceleratorType.CPU,
        device_type='n2-standard-32-8',
        supports_sub_slicing=False,
        supports_super_slicing=False,
        supports_accelerator_network_profile=False,
        docker_platform=AMD_PLATFORM,
    ),
    'n2-standard-32-16': SystemCharacteristics(
        topology='N/A',
        vms_per_slice=16,
        gke_accelerator='N/A',
        gce_machine_type='n2-standard-32',
        chips_per_vm=32,
        accelerator_type=AcceleratorType.CPU,
        device_type='n2-standard-32-16',
        supports_sub_slicing=False,
        supports_super_slicing=False,
        supports_accelerator_network_profile=False,
        docker_platform=AMD_PLATFORM,
    ),
    'n2-standard-32-32': SystemCharacteristics(
        topology='N/A',
        vms_per_slice=32,
        gke_accelerator='N/A',
        gce_machine_type='n2-standard-32',
        chips_per_vm=32,
        accelerator_type=AcceleratorType.CPU,
        device_type='n2-standard-32-32',
        supports_sub_slicing=False,
        supports_super_slicing=False,
        supports_accelerator_network_profile=False,
        docker_platform=AMD_PLATFORM,
    ),
    'n2-standard-32-64': SystemCharacteristics(
        topology='N/A',
        vms_per_slice=64,
        gke_accelerator='N/A',
        gce_machine_type='n2-standard-32',
        chips_per_vm=32,
        accelerator_type=AcceleratorType.CPU,
        device_type='n2-standard-32-64',
        supports_sub_slicing=False,
        supports_super_slicing=False,
        supports_accelerator_network_profile=False,
        docker_platform=AMD_PLATFORM,
    ),
    'n2-standard-32-128': SystemCharacteristics(
        topology='N/A',
        vms_per_slice=128,
        gke_accelerator='N/A',
        gce_machine_type='n2-standard-32',
        chips_per_vm=32,
        accelerator_type=AcceleratorType.CPU,
        device_type='n2-standard-32-128',
        supports_sub_slicing=False,
        supports_super_slicing=False,
        supports_accelerator_network_profile=False,
        docker_platform=AMD_PLATFORM,
    ),
    'n2-standard-32-256': SystemCharacteristics(
        topology='N/A',
        vms_per_slice=256,
        gke_accelerator='N/A',
        gce_machine_type='n2-standard-32',
        chips_per_vm=32,
        accelerator_type=AcceleratorType.CPU,
        device_type='n2-standard-32-256',
        supports_sub_slicing=False,
        supports_super_slicing=False,
        supports_accelerator_network_profile=False,
        docker_platform=AMD_PLATFORM,
    ),
    'n2-standard-32-512': SystemCharacteristics(
        topology='N/A',
        vms_per_slice=512,
        gke_accelerator='N/A',
        gce_machine_type='n2-standard-32',
        chips_per_vm=32,
        accelerator_type=AcceleratorType.CPU,
        device_type='n2-standard-32-512',
        supports_sub_slicing=False,
        supports_super_slicing=False,
        supports_accelerator_network_profile=False,
        docker_platform=AMD_PLATFORM,
    ),
    'n2-standard-32-1024': SystemCharacteristics(
        topology='N/A',
        vms_per_slice=1024,
        gke_accelerator='N/A',
        gce_machine_type='n2-standard-32',
        chips_per_vm=32,
        accelerator_type=AcceleratorType.CPU,
        device_type='n2-standard-32-1024',
        supports_sub_slicing=False,
        supports_super_slicing=False,
        supports_accelerator_network_profile=False,
        docker_platform=AMD_PLATFORM,
    ),
    'n2-standard-32-2048': SystemCharacteristics(
        topology='N/A',
        vms_per_slice=2048,
        gke_accelerator='N/A',
        gce_machine_type='n2-standard-32',
        chips_per_vm=32,
        accelerator_type=AcceleratorType.CPU,
        device_type='n2-standard-32-2048',
        supports_sub_slicing=False,
        supports_super_slicing=False,
        supports_accelerator_network_profile=False,
        docker_platform=AMD_PLATFORM,
    ),
}
""" If you modify UserFacingNameToSystemCharacteristics you should also modify
the corresponding Map in MaxText/accelerator_to_spec_map.py """


def get_system_characteristics_keys_by_accelerator_type(
    accelerators: list[AcceleratorType] | None = None,
) -> list[str]:
  """Returns UserFacingNameToSystemCharacteristics keys for given AcceleratorTypes."""
  if accelerators is None:
    accelerators = list(AcceleratorType)
  return [
      key
      for key, value in UserFacingNameToSystemCharacteristics.items()
      if value.accelerator_type in accelerators
  ]


def create_accelerator_label(system: SystemCharacteristics) -> str:
  if system.accelerator_type == AcceleratorType.CPU:
    return ''
  return (
      f'{AcceleratorTypeToAcceleratorCharacteristics[system.accelerator_type].accelerator_label}:'
      f' {system.gke_accelerator}'
  )


def create_machine_label(system: SystemCharacteristics) -> str:
  if system.accelerator_type == AcceleratorType.TPU:
    return (
        f'{AcceleratorTypeToAcceleratorCharacteristics[AcceleratorType.TPU].machine_label}:'
        f' {system.topology}'
    )
  return ''
