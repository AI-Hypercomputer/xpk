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

from .scheduling import create_sub_slicing_annotations, create_placement_policy_label, get_placement_policy_name, is_placement_policy_supported
from .system_characteristics import SystemCharacteristics, AcceleratorType


def test_create_sub_slicing_annotations_returns_valid_annotations():
  result = create_sub_slicing_annotations(sub_slicing_topology='2x4')

  assert result == [
      (
          'kueue.x-k8s.io/podset-required-topology:'
          ' "cloud.google.com/gke-tpu-slice-2x4-id"'
      ),
      'cloud.google.com/gke-tpu-slice-topology: 2x4',
  ]


def test_create_placement_policy_label_returns_valid_label():
  system_characteristics = SystemCharacteristics(
      chips_per_vm=1,
      gce_machine_type='tpu7x-standard-1t',
      gke_accelerator='tpu7x',
      requires_workload_policy=False,
      topology='1x1x1',
      vms_per_slice=1,
      device_type='tpu7x',
      accelerator_type=AcceleratorType.TPU,
      supports_sub_slicing=False,
  )
  label = create_placement_policy_label(system_characteristics)
  assert (
      label
      == 'cloud.google.com/placement-policy-name: tpu7x-1x1x1-placement-policy'
  )


def test_get_placement_policy_name_returns_valid_name():
  system_characteristics = SystemCharacteristics(
      chips_per_vm=1,
      gce_machine_type='tpu7x-standard-1t',
      gke_accelerator='tpu7x',
      requires_workload_policy=False,
      topology='1x1x1',
      vms_per_slice=1,
      device_type='tpu7x',
      accelerator_type=AcceleratorType.TPU,
      supports_sub_slicing=False,
  )
  name = get_placement_policy_name(system_characteristics)
  assert name == 'tpu7x-1x1x1-placement-policy'


def test_is_placement_policy_supported_returns_true_for_system_characteristics_supporting_workload_policy_and_having_valid_topology():
  system_characteristics = SystemCharacteristics(
      chips_per_vm=1,
      gce_machine_type='tpu7x-standard-1t',
      gke_accelerator='tpu7x',
      requires_workload_policy=True,
      topology='1x1x1',
      vms_per_slice=1,
      device_type='tpu7x',
      accelerator_type=AcceleratorType.TPU,
      supports_sub_slicing=False,
  )
  assert is_placement_policy_supported(system_characteristics) is True


def test_is_placement_policy_supported_returns_false_for_system_characteristics_not_supporting_workload_policy_and_having_valid_topology():
  system_characteristics = SystemCharacteristics(
      chips_per_vm=1,
      gce_machine_type='tpu7x-standard-1t',
      gke_accelerator='tpu7x',
      requires_workload_policy=False,
      topology='1x1x1',
      vms_per_slice=1,
      device_type='tpu7x',
      accelerator_type=AcceleratorType.TPU,
      supports_sub_slicing=False,
  )
  assert is_placement_policy_supported(system_characteristics) is False


def test_is_placement_policy_supported_returns_false_for_system_characteristics_supporting_workload_policy_and_having_invalid_topology():
  system_characteristics = SystemCharacteristics(
      chips_per_vm=1,
      gce_machine_type='tpu7x-standard-1t',
      gke_accelerator='tpu7x',
      requires_workload_policy=True,
      topology='aaa',
      vms_per_slice=1,
      device_type='tpu7x',
      accelerator_type=AcceleratorType.TPU,
      supports_sub_slicing=False,
  )
  assert is_placement_policy_supported(system_characteristics) is False
