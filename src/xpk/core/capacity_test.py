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

from .capacity import (
    get_capacity_type,
    CapacityType,
)
from xpk.core.testing.commands_tester import CommandsTester
from .system_characteristics import SystemCharacteristics, AcceleratorType, DockerPlatform


@pytest.fixture
def commands_tester(mocker):
  return CommandsTester(mocker)


@pytest.fixture
def test_system():
  return SystemCharacteristics(
      topology='2x2x1',
      vms_per_slice=1,
      gke_accelerator='test-accel',
      gce_machine_type='test-machine',
      chips_per_vm=1,
      accelerator_type=AcceleratorType.TPU,
      device_type='test-device',
      supports_sub_slicing=False,
      supports_super_slicing=False,
      supports_accelerator_network_profile=False,
      docker_platform=DockerPlatform.AMD,
  )


def test_get_capacity_type_multiple_reservations(mocker):
  mocker.patch('xpk.core.capacity.verify_reservations_exist', return_value=0)
  args = mocker.Mock(
      on_demand=False,
      reservation='res1,res2',
      spot=False,
      flex=False,
      project='project',
      zone='zone',
  )

  capacity_type, return_code = get_capacity_type(args)

  assert capacity_type == CapacityType.RESERVATION
  assert return_code == 0
