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

from .system_characteristics import get_tpu_system_characteristics_map, SystemCharacteristics


def test_get_tpu_system_characteristics_map_returns_correct_values_for_1x1_topology():
  result = get_tpu_system_characteristics_map(
      prefix="test",
      tensorcores_per_chip=1,
      gke_accelerator="test",
      machine_type="test",
      supported_topologies=["1x1"],
      supports_sub_slicing=False,
      requires_workload_policy=True,
  )

  expected_system_characteristics = SystemCharacteristics(
      topology="1x1",
      vms_per_slice=1,
      gke_accelerator="test",
      gce_machine_type="test",
      chips_per_vm=1,
      accelerator_type=1,
      device_type="test-1",
      supports_sub_slicing=False,
      requires_workload_policy=True,
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
      supports_sub_slicing=False,
      requires_workload_policy=True,
  )

  expected_system_characteristics = SystemCharacteristics(
      topology="2x2",
      vms_per_slice=1,
      gke_accelerator="test",
      gce_machine_type="test",
      chips_per_vm=4,
      accelerator_type=1,
      device_type="test-8",
      supports_sub_slicing=False,
      requires_workload_policy=True,
  )
  assert result == {
      "test-8": expected_system_characteristics,
      "test-2x2": expected_system_characteristics,
  }
