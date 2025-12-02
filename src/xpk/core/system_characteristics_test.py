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

import pytest
from .system_characteristics import (
    get_tpu_system_characteristics_map,
    generate_tpu_topologies,
    DockerPlatform,
    SystemCharacteristics,
    AcceleratorType,
    GpuConfig,
)


def test_get_tpu_system_characteristics_map_returns_correct_values_for_1x1_topology():
  result = get_tpu_system_characteristics_map(
      prefix="test",
      tensorcores_per_chip=1,
      gke_accelerator="test",
      machine_type="test",
      supported_topologies=["1x1"],
      docker_platform=DockerPlatform.AMD,
      tpu_type_requires_workload_policy=False,
  )

  expected_system_characteristics = SystemCharacteristics(
      topology="1x1",
      vms_per_slice=1,
      gke_accelerator="test",
      gce_machine_type="test",
      chips_per_vm=1,
      accelerator_type=AcceleratorType.TPU,
      device_type="test-1",
      supports_sub_slicing=False,
      supports_super_slicing=False,
      docker_platform=DockerPlatform.AMD,
      requires_workload_policy=False,
  )
  assert result == {
      "test-1": expected_system_characteristics,
      "test-1x1": expected_system_characteristics,
  }


def test_get_tpu_system_characteristics_map_returns_correct_values_for_2x2_topology():
  result = get_tpu_system_characteristics_map(
      prefix="test",
      tensorcores_per_chip=2,
      gke_accelerator="test",
      machine_type="test",
      supported_topologies=["2x2"],
      docker_platform=DockerPlatform.AMD,
      tpu_type_requires_workload_policy=True,
  )

  expected_system_characteristics = SystemCharacteristics(
      topology="2x2",
      vms_per_slice=1,
      gke_accelerator="test",
      gce_machine_type="test",
      chips_per_vm=4,
      accelerator_type=AcceleratorType.TPU,
      device_type="test-8",
      supports_sub_slicing=False,
      supports_super_slicing=False,
      docker_platform=DockerPlatform.AMD,
      requires_workload_policy=False,
  )
  assert result == {
      "test-8": expected_system_characteristics,
      "test-2x2": expected_system_characteristics,
  }


def test_get_tpu_system_characteristics_map_returns_correct_values_for_2x2x2_topology():
  result = get_tpu_system_characteristics_map(
      prefix="test",
      tensorcores_per_chip=2,
      gke_accelerator="test",
      machine_type="test",
      supported_topologies=["2x2x2"],
      docker_platform=DockerPlatform.AMD,
      tpu_type_requires_workload_policy=True,
  )

  expected_system_characteristics = SystemCharacteristics(
      topology="2x2x2",
      vms_per_slice=2,
      gke_accelerator="test",
      gce_machine_type="test",
      chips_per_vm=4,
      accelerator_type=AcceleratorType.TPU,
      device_type="test-16",
      supports_sub_slicing=False,
      supports_super_slicing=False,
      docker_platform=DockerPlatform.AMD,
      requires_workload_policy=True,
  )
  assert result == {
      "test-16": expected_system_characteristics,
      "test-2x2x2": expected_system_characteristics,
  }


def test_get_tpu_system_characteristics_map_sets_sub_slicing_support():
  result = get_tpu_system_characteristics_map(
      prefix="test",
      tensorcores_per_chip=2,
      gke_accelerator="test",
      machine_type="test",
      supported_topologies=["4x4x4", "4x4x8", "4x4x16"],
      docker_platform=DockerPlatform.AMD,
      sub_slicing_topologies=set(["4x4x8", "4x4x16"]),
  )

  assert result["test-4x4x4"].supports_sub_slicing is False
  assert result["test-4x4x8"].supports_sub_slicing is True
  assert result["test-4x4x16"].supports_sub_slicing is True


def test_get_tpu_system_characteristics_map_sets_super_slicing_support():
  result = get_tpu_system_characteristics_map(
      prefix="test",
      tensorcores_per_chip=2,
      gke_accelerator="test",
      machine_type="test",
      supported_topologies=["4x4x4", "4x4x8", "4x4x16"],
      docker_platform=DockerPlatform.AMD,
      super_slicing_topologies=set(["4x4x8", "4x4x16"]),
  )

  assert result["test-4x4x4"].supports_super_slicing is False
  assert result["test-4x4x8"].supports_super_slicing is True
  assert result["test-4x4x16"].supports_super_slicing is True


def test_get_tpu_system_characteristics_map_prefers_default_topologies():
  result = get_tpu_system_characteristics_map(
      prefix="test",
      tensorcores_per_chip=2,
      gke_accelerator="test",
      machine_type="test",
      supported_topologies=["4x4x4", "4x4x32", "4x8x16", "8x8x8"],
      docker_platform=DockerPlatform.AMD,
      default_topologies=set(["4x8x16"]),
  )

  assert result["test-128"].topology == "4x4x4"
  assert result["test-1024"].topology == "4x8x16"


def test_generate_tpu_topologies_returns_correct_number_of_values_for_TPU_platforms():
  v4 = generate_tpu_topologies(max_cubes=64, enforce_nondecreasing=False)
  v5p = generate_tpu_topologies(max_cubes=140)
  tpu7x = generate_tpu_topologies(max_cubes=144)

  assert len(v4) == 800
  assert len(v5p) == 414
  assert len(tpu7x) == 432


def test_generate_tpu_topologies_respects_constraints():
  ordered_6_cubes = generate_tpu_topologies(
      max_cubes=6, enforce_nondecreasing=True
  )
  non_ordered_6_cubes = generate_tpu_topologies(
      max_cubes=6, enforce_nondecreasing=False
  )

  assert "8x4x4" not in ordered_6_cubes
  assert "8x4x4" in non_ordered_6_cubes
  assert "4x8x12" in ordered_6_cubes  # exactly 6 cubes
  assert "4x8x12" in non_ordered_6_cubes  # exactly 6 cubes
  assert "4x8x16" not in ordered_6_cubes  # too many cubes (8)
  assert "4x8x16" not in non_ordered_6_cubes  # too many cubes (8)


def test_generate_tpu_topologies_contains_sub_cube_slices():
  one_cube = generate_tpu_topologies(max_cubes=1)

  assert one_cube == ["2x2x1", "2x2x2", "2x2x4", "2x4x4", "4x4x4"]


def test_system_characteristics_post_init_sets_workload_policy_for_gpu():
  """Tests that __post_init__ correctly sets requires_workload_policy for GPUs."""
  gpu_system = SystemCharacteristics(
      topology="N/A",
      vms_per_slice=1,
      gke_accelerator="nvidia-l4",
      gce_machine_type="g2-standard-12",
      chips_per_vm=1,
      accelerator_type=AcceleratorType.GPU,
      device_type="l4-1",
      supports_sub_slicing=False,
      supports_super_slicing=False,
      docker_platform=DockerPlatform.AMD,
      gpu_config=GpuConfig(requires_topology=False),
  )
  assert gpu_system.requires_workload_policy is True


def test_system_characteristics_post_init_throws_for_gpu_without_config():
  """Tests that __post_init__ raises ValueError for GPU without gpu_config."""
  with pytest.raises(ValueError, match="'gpu_config' was not provided"):
    SystemCharacteristics(
        topology="N/A",
        vms_per_slice=1,
        gke_accelerator="nvidia-l4",
        gce_machine_type="g2-standard-12",
        chips_per_vm=1,
        accelerator_type=AcceleratorType.GPU,
        device_type="l4-1",
        supports_sub_slicing=False,
        supports_super_slicing=False,
        docker_platform=DockerPlatform.AMD,
    )
