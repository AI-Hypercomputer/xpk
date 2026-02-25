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
from typing import Iterator
from unittest.mock import patch

from .capacity import (
    get_capacity_type,
    CapacityType,
    assess_available_slices,
    ReservationLink,
    BlockReservationLink,
    SubBlockReservationLink,
    ReservationCapacity,
)
from .reservation import (
    _get_reservation_cached,
    get_reservation_accelerator_type,
    SpecificReservation,
    AggregateReservation,
    AcceleratorResource,
)
from .testing.commands_tester import CommandsTester
from .testing.mock_reservation import (
    setup_mock_reservation,
    MockBlock,
    MockSubBlock,
)
from .system_characteristics import SystemCharacteristics, AcceleratorType, DockerPlatform, GpuConfig


@pytest.fixture
def commands_tester(mocker) -> CommandsTester:
  return CommandsTester(mocker)


@pytest.fixture(autouse=True)
def clear_capacity_cache() -> Iterator[None]:
  _get_reservation_cached.cache_clear()
  yield
  _get_reservation_cached.cache_clear()


@pytest.fixture
def test_system() -> SystemCharacteristics:
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


def test_assess_available_slices_sub_block_healthy(
    commands_tester: CommandsTester,
    test_system: SystemCharacteristics,
):
  setup_mock_reservation(
      commands_tester,
      specific_reservation=SpecificReservation(
          count=6, in_use_count=1, machine_type='test-machine'
      ),
      blocks=[
          MockBlock(
              name='block',
              sub_blocks=[MockSubBlock(count=6, in_use_count=1)],
          )
      ],
  )
  res = SubBlockReservationLink(
      project='project',
      name='reservation',
      zone='zone',
      block_name='block',
      sub_block_name='sub-block',
  )

  slices, return_code = assess_available_slices(
      [res],
      force_sub_block_targeting=False,
      system=test_system,
      vms_per_slice=2,
  )

  assert slices == [ReservationCapacity(res, 2)]
  assert return_code == 0


def test_assess_available_slices_sub_block_unhealthy(
    commands_tester: CommandsTester,
    test_system: SystemCharacteristics,
):
  setup_mock_reservation(
      commands_tester,
      specific_reservation=SpecificReservation(
          count=48, in_use_count=2, machine_type='test-machine'
      ),
      blocks=[MockBlock(name='block', sub_blocks=[])],
  )
  res = SubBlockReservationLink(
      project='project',
      name='reservation',
      zone='zone',
      block_name='block',
      sub_block_name='sub-block',
  )
  slices, return_code = assess_available_slices(
      [res],
      force_sub_block_targeting=False,
      system=test_system,
      vms_per_slice=test_system.vms_per_slice,
  )

  assert not slices
  assert return_code == 1


def test_assess_available_slices_block_healthy(
    commands_tester: CommandsTester, test_system: SystemCharacteristics
):
  setup_mock_reservation(
      commands_tester,
      specific_reservation=SpecificReservation(
          count=10, in_use_count=2, machine_type='test-machine'
      ),
      blocks=[
          MockBlock(
              name='block',
              sub_blocks=[
                  MockSubBlock(name='sub1', count=4, in_use_count=1),
                  MockSubBlock(name='sub2', count=6, in_use_count=1),
              ],
          )
      ],
  )
  res = BlockReservationLink(
      project='project',
      name='reservation',
      zone='zone',
      block_name='block',
  )

  slices, return_code = assess_available_slices(
      [res],
      force_sub_block_targeting=True,
      system=test_system,
      vms_per_slice=2,
  )

  assert return_code == 0
  assert slices == [
      ReservationCapacity(
          SubBlockReservationLink(
              project='project',
              name='reservation',
              zone='zone',
              block_name='block',
              sub_block_name='sub1',
          ),
          available_slices=1,
      ),
      ReservationCapacity(
          SubBlockReservationLink(
              project='project',
              name='reservation',
              zone='zone',
              block_name='block',
              sub_block_name='sub2',
          ),
          available_slices=2,
      ),
  ]


def test_assess_available_slices_block_unhealthy(
    commands_tester: CommandsTester,
    test_system: SystemCharacteristics,
):
  setup_mock_reservation(
      commands_tester,
      specific_reservation=SpecificReservation(
          count=48, in_use_count=2, machine_type='test-machine'
      ),
      blocks=[MockBlock(name='block', sub_blocks=[])],
  )
  res = BlockReservationLink(
      project='project',
      name='reservation',
      zone='zone',
      block_name='block',
  )

  slices, return_code = assess_available_slices(
      [res],
      force_sub_block_targeting=True,
      system=test_system,
      vms_per_slice=test_system.vms_per_slice,
  )

  assert not slices
  assert return_code == 1


def test_assess_available_slices_reservation_with_sub_block_targeting(
    commands_tester: CommandsTester,
    test_system: SystemCharacteristics,
):
  setup_mock_reservation(
      commands_tester,
      specific_reservation=SpecificReservation(
          count=48, in_use_count=2, machine_type='test-machine'
      ),
      blocks=[
          MockBlock(
              name='block1',
              sub_blocks=[MockSubBlock(name='sub1', count=1, in_use_count=0)],
          )
      ],
  )

  res = ReservationLink(project='project', name='reservation', zone='zone')
  slices, return_code = assess_available_slices(
      [res],
      force_sub_block_targeting=True,
      system=test_system,
      vms_per_slice=test_system.vms_per_slice,
  )

  assert return_code == 0
  assert slices == [
      ReservationCapacity(
          SubBlockReservationLink(
              project='project',
              name='reservation',
              zone='zone',
              block_name='block1',
              sub_block_name='sub1',
          ),
          available_slices=1,
      )
  ]


def test_assess_available_slices_reservation_without_sub_block_targeting(
    commands_tester: CommandsTester,
    test_system: SystemCharacteristics,
):
  setup_mock_reservation(
      commands_tester,
      specific_reservation=SpecificReservation(
          count=10, in_use_count=4, machine_type='test-machine'
      ),
      blocks=[],
  )

  res = ReservationLink(project='project', name='reservation', zone='zone')
  slices, return_code = assess_available_slices(
      [res],
      force_sub_block_targeting=False,
      system=test_system,
      vms_per_slice=3,
  )

  assert return_code == 0
  assert slices == [
      ReservationCapacity(
          ReservationLink(project='project', name='reservation', zone='zone'),
          available_slices=2,
      )
  ]


def test_assess_available_slices_reservation_without_blocks_sub_block_targeting(
    commands_tester: CommandsTester,
    test_system: SystemCharacteristics,
):
  setup_mock_reservation(
      commands_tester,
      specific_reservation=SpecificReservation(
          count=2, in_use_count=0, machine_type='test-machine'
      ),
      blocks=[],
  )

  res = ReservationLink(project='project', name='reservation', zone='zone')
  slices, return_code = assess_available_slices(
      [res],
      force_sub_block_targeting=True,
      system=test_system,
      vms_per_slice=test_system.vms_per_slice,
  )

  assert return_code == 1
  assert not slices


@pytest.mark.parametrize(
    argnames='link',
    argvalues=[
        ReservationLink(
            project='project',
            name='reservation',
            zone='zone',
        ),
        BlockReservationLink(
            project='project',
            name='reservation',
            zone='zone',
            block_name='block',
        ),
        SubBlockReservationLink(
            project='project',
            name='reservation',
            zone='zone',
            block_name='block',
            sub_block_name='sub-block',
        ),
    ],
)
def test_assess_available_slices_insufficient_hosts(
    commands_tester: CommandsTester,
    test_system: SystemCharacteristics,
    link: ReservationLink | BlockReservationLink | SubBlockReservationLink,
):
  setup_mock_reservation(
      commands_tester,
      specific_reservation=SpecificReservation(
          count=16, in_use_count=2, machine_type='test-machine'
      ),
      blocks=[
          MockBlock(
              name='block',
              sub_blocks=[
                  MockSubBlock(name='sub-block', count=16, in_use_count=2)
              ],
          )
      ],
  )

  slices, return_code = assess_available_slices(
      [link],
      force_sub_block_targeting=True,
      system=test_system,
      vms_per_slice=16,
  )

  assert not slices
  assert return_code == 1


@patch('xpk.core.capacity.project_id_to_project_number', return_value='12345')
def test_assess_available_slices_aggregate_reservation(
    mock_project_id,
    commands_tester: CommandsTester,
    test_system: SystemCharacteristics,
):
  # For TPU, target type includes project number and zone
  target_type = f'projects/12345/zones/zone/acceleratorTypes/{get_reservation_accelerator_type(test_system)}'
  aggregate_payload = AggregateReservation(
      reserved_resources=[
          AcceleratorResource(
              accelerator_type=target_type, accelerator_count=100
          ),
          AcceleratorResource(
              accelerator_type='wrong-type', accelerator_count=100
          ),
      ],
      in_use_resources=[
          AcceleratorResource(
              accelerator_type=target_type, accelerator_count=20
          ),
          AcceleratorResource(
              accelerator_type='accelerator-2', accelerator_count=50
          ),
      ],
  )
  setup_mock_reservation(
      commands_tester,
      aggregate_reservation=aggregate_payload,
  )
  res = ReservationLink(project='project', name='reservation', zone='zone')

  slices, return_code = assess_available_slices(
      [res],
      force_sub_block_targeting=False,
      system=test_system,
      vms_per_slice=test_system.vms_per_slice,
  )

  assert return_code == 0
  assert slices == [
      ReservationCapacity(
          ReservationLink(project='project', name='reservation', zone='zone'),
          available_slices=80,
      )
  ]


def test_assess_available_slices_failures_sub_block_check(
    commands_tester: CommandsTester,
    test_system: SystemCharacteristics,
):
  setup_mock_reservation(
      commands_tester,
      specific_reservation=SpecificReservation(
          count=100, in_use_count=0, machine_type='test-machine'
      ),
  )
  res_sub = SubBlockReservationLink(
      project='project',
      name='reservation',
      zone='zone',
      block_name='block',
      sub_block_name='sub-block',
  )
  commands_tester.set_result_for_command(
      (1, ''), 'gcloud beta compute reservations sub-blocks list'
  )

  slices, return_code = assess_available_slices(
      [res_sub],
      force_sub_block_targeting=False,
      system=test_system,
      vms_per_slice=test_system.vms_per_slice,
  )

  assert not slices
  assert return_code == 1


def test_assess_available_slices_failures_block_sub_blocks_check(
    commands_tester: CommandsTester,
    test_system: SystemCharacteristics,
):
  setup_mock_reservation(
      commands_tester,
      specific_reservation=SpecificReservation(
          count=100, in_use_count=0, machine_type='test-machine'
      ),
  )
  res_block = BlockReservationLink(
      project='project',
      name='reservation',
      zone='zone',
      block_name='block',
  )
  commands_tester.set_result_for_command(
      (1, ''), 'gcloud beta compute reservations sub-blocks list'
  )

  slices, return_code = assess_available_slices(
      [res_block],
      force_sub_block_targeting=True,
      system=test_system,
      vms_per_slice=test_system.vms_per_slice,
  )

  assert not slices
  assert return_code == 1


def test_assess_available_slices_failures_reservation_blocks_check(
    commands_tester: CommandsTester,
    test_system: SystemCharacteristics,
):
  setup_mock_reservation(
      commands_tester,
      specific_reservation=SpecificReservation(
          count=100, in_use_count=0, machine_type='test-machine'
      ),
  )
  res = ReservationLink(project='project', name='reservation', zone='zone')
  commands_tester.set_result_for_command(
      (1, ''), 'gcloud beta compute reservations blocks list'
  )

  slices, return_code = assess_available_slices(
      [res],
      force_sub_block_targeting=True,
      system=test_system,
      vms_per_slice=test_system.vms_per_slice,
  )

  assert not slices
  assert return_code == 1


def test_assess_available_slices_failures_reservation_count_check(
    commands_tester: CommandsTester,
    test_system: SystemCharacteristics,
):
  res = ReservationLink(project='project', name='reservation', zone='zone')
  commands_tester.set_result_for_command(
      (1, ''), 'gcloud beta compute reservations describe'
  )

  slices, return_code = assess_available_slices(
      [res],
      force_sub_block_targeting=False,
      system=test_system,
      vms_per_slice=test_system.vms_per_slice,
  )

  assert not slices
  assert return_code == 1


def test_assess_available_slices_mixed_reservations_with_subblock_targeting(
    commands_tester: CommandsTester,
    test_system: SystemCharacteristics,
):
  setup_mock_reservation(
      commands_tester,
      specific_reservation=SpecificReservation(
          count=48, in_use_count=2, machine_type='test-machine'
      ),
      blocks=[
          MockBlock(
              name='block10',
              sub_blocks=[
                  MockSubBlock(name='sub11', count=1, in_use_count=0),
                  MockSubBlock(name='sub12', count=1, in_use_count=0),
              ],
          ),
          MockBlock(
              name='block20',
              sub_blocks=[MockSubBlock(name='sub21', count=1, in_use_count=0)],
          ),
          MockBlock(
              name='block30',
              sub_blocks=[MockSubBlock(name='sub31', count=1, in_use_count=0)],
          ),
          MockBlock(name='block40', sub_blocks=[]),
      ],
  )

  reservation_link = ReservationLink(
      project='project', name='res1', zone='zone'
  )
  block_link = BlockReservationLink(
      project='project', name='res1', zone='zone', block_name='block10'
  )
  sub_block_link = SubBlockReservationLink(
      project='project',
      name='res1',
      zone='zone',
      block_name='block20',
      sub_block_name='sub21',
  )

  slices, return_code = assess_available_slices(
      [block_link, sub_block_link, reservation_link],
      force_sub_block_targeting=True,
      system=test_system,
      vms_per_slice=test_system.vms_per_slice,
  )

  assert return_code == 0
  assert slices == [
      ReservationCapacity(
          SubBlockReservationLink(
              project='project',
              name='res1',
              zone='zone',
              block_name='block10',
              sub_block_name='sub11',
          ),
          available_slices=1,
      ),
      ReservationCapacity(
          SubBlockReservationLink(
              project='project',
              name='res1',
              zone='zone',
              block_name='block10',
              sub_block_name='sub12',
          ),
          available_slices=1,
      ),
      ReservationCapacity(
          SubBlockReservationLink(
              project='project',
              name='res1',
              zone='zone',
              block_name='block20',
              sub_block_name='sub21',
          ),
          available_slices=1,
      ),
      ReservationCapacity(
          SubBlockReservationLink(
              project='project',
              name='res1',
              zone='zone',
              block_name='block30',
              sub_block_name='sub31',
          ),
          available_slices=1,
      ),
  ]


def test_assess_available_slices_tpu_reservation_success(
    commands_tester: CommandsTester, test_system: SystemCharacteristics
):
  setup_mock_reservation(
      commands_tester,
      specific_reservation=SpecificReservation(
          count=10, in_use_count=2, machine_type='test-machine'
      ),
  )
  res_link = ReservationLink(project='p', name='r', zone='z')

  capacity, return_code = assess_available_slices(
      [res_link],
      force_sub_block_targeting=False,
      system=test_system,
      vms_per_slice=test_system.vms_per_slice,
  )

  assert return_code == 0
  assert capacity[0].available_slices == 8


def test_assess_available_slices_tpu_reservation_failure(
    commands_tester: CommandsTester, test_system: SystemCharacteristics
):
  setup_mock_reservation(
      commands_tester,
      specific_reservation=SpecificReservation(
          count=10, in_use_count=2, machine_type='wrong-machine'
      ),
  )
  res_link_fail = ReservationLink(project='p', name='r-fail', zone='z')

  capacity, return_code = assess_available_slices(
      [res_link_fail],
      force_sub_block_targeting=False,
      system=test_system,
      vms_per_slice=test_system.vms_per_slice,
  )

  assert return_code == 1
  assert not capacity


def test_assess_available_slices_gpu_reservation_success(
    commands_tester: CommandsTester,
):
  gpu_system = SystemCharacteristics(
      topology='N/A',
      vms_per_slice=1,
      gke_accelerator='nvidia-test',
      gce_machine_type='g2-standard-12',
      chips_per_vm=1,
      accelerator_type=AcceleratorType.GPU,
      device_type='test-gpu',
      supports_sub_slicing=False,
      supports_super_slicing=False,
      supports_accelerator_network_profile=False,
      docker_platform=DockerPlatform.AMD,
      gpu_config=GpuConfig(requires_topology=False),
  )
  setup_mock_reservation(
      commands_tester,
      specific_reservation=SpecificReservation(
          count=10,
          in_use_count=2,
          machine_type='test-machine',
          guest_accelerators=[
              AcceleratorResource(
                  accelerator_type='nvidia-test', accelerator_count=1
              )
          ],
      ),
  )
  res_link = ReservationLink(project='p', name='r', zone='z')

  capacity, return_code = assess_available_slices(
      [res_link],
      force_sub_block_targeting=False,
      system=gpu_system,
      vms_per_slice=gpu_system.vms_per_slice,
  )

  assert return_code == 0
  assert capacity[0].available_slices == 8


def test_assess_available_slices_gpu_reservation_failure(
    commands_tester: CommandsTester,
):
  gpu_system = SystemCharacteristics(
      topology='N/A',
      vms_per_slice=1,
      gke_accelerator='nvidia-test',
      gce_machine_type='g2-standard-12',
      chips_per_vm=1,
      accelerator_type=AcceleratorType.GPU,
      device_type='test-gpu',
      supports_sub_slicing=False,
      supports_super_slicing=False,
      supports_accelerator_network_profile=False,
      docker_platform=DockerPlatform.AMD,
      gpu_config=GpuConfig(requires_topology=False),
  )
  setup_mock_reservation(
      commands_tester,
      specific_reservation=SpecificReservation(
          count=10,
          in_use_count=2,
          machine_type='test-machine',
          guest_accelerators=[
              AcceleratorResource(
                  accelerator_type='nvidia-wrong', accelerator_count=1
              )
          ],
      ),
  )
  res_link_fail = ReservationLink(project='p', name='r-fail', zone='z')

  capacity, return_code = assess_available_slices(
      [res_link_fail],
      force_sub_block_targeting=False,
      system=gpu_system,
      vms_per_slice=gpu_system.vms_per_slice,
  )

  assert return_code == 1
  assert not capacity


def test_assess_available_slices_gpu_reservation_with_vms_per_slice(
    commands_tester: CommandsTester,
):
  gpu_system = SystemCharacteristics(
      topology='N/A',
      vms_per_slice=1,
      gke_accelerator='nvidia-test',
      gce_machine_type='g2-standard-12',
      chips_per_vm=1,
      accelerator_type=AcceleratorType.GPU,
      device_type='test-gpu',
      supports_sub_slicing=False,
      supports_super_slicing=False,
      supports_accelerator_network_profile=False,
      docker_platform=DockerPlatform.AMD,
      gpu_config=GpuConfig(requires_topology=False),
  )
  setup_mock_reservation(
      commands_tester,
      specific_reservation=SpecificReservation(
          count=10,
          in_use_count=2,
          machine_type='test-machine',
          guest_accelerators=[
              AcceleratorResource(
                  accelerator_type='nvidia-test', accelerator_count=1
              )
          ],
      ),
  )
  res_link = ReservationLink(project='p', name='r', zone='z')

  # Request 2 VMs per slice (e.g. num-nodes=2)
  capacity, return_code = assess_available_slices(
      [res_link],
      force_sub_block_targeting=False,
      system=gpu_system,
      vms_per_slice=2,
  )

  assert return_code == 0
  assert capacity[0].available_slices == 4


@patch('xpk.core.capacity.project_id_to_project_number', return_value='12345')
def test_assess_available_slices_aggregate_reservation_failure(
    mock_project_id,
    commands_tester: CommandsTester,
    test_system: SystemCharacteristics,
):
  # For TPU, target type includes project number and zone
  # This setup simulates a mismatch.
  aggregate_payload = AggregateReservation(
      reserved_resources=[
          AcceleratorResource(
              accelerator_type='wrong-type', accelerator_count=100
          )
      ],
      in_use_resources=[],
  )
  setup_mock_reservation(
      commands_tester,
      aggregate_reservation=aggregate_payload,
  )
  res = ReservationLink(project='project', name='reservation', zone='zone')

  slices, return_code = assess_available_slices(
      [res],
      force_sub_block_targeting=False,
      system=test_system,
      vms_per_slice=test_system.vms_per_slice,
  )

  assert return_code == 1
  assert not slices


def test_assess_available_slices_cpu_reservation_success(
    commands_tester: CommandsTester,
):
  cpu_system = SystemCharacteristics(
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
      docker_platform=DockerPlatform.AMD,
  )

  setup_mock_reservation(
      commands_tester,
      specific_reservation=SpecificReservation(
          count=10, in_use_count=2, machine_type='n2-standard-32'
      ),
  )
  res_link = ReservationLink(project='p', name='r', zone='z')

  capacity, return_code = assess_available_slices(
      [res_link],
      force_sub_block_targeting=False,
      system=cpu_system,
      vms_per_slice=cpu_system.vms_per_slice,
  )

  assert return_code == 0
  assert capacity[0].available_slices == 8


def test_assess_available_slices_cpu_reservation_failure(
    commands_tester: CommandsTester,
):
  cpu_system = SystemCharacteristics(
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
      docker_platform=DockerPlatform.AMD,
  )

  setup_mock_reservation(
      commands_tester,
      specific_reservation=SpecificReservation(
          count=10, in_use_count=2, machine_type='n2-standard-64'
      ),
  )
  res_link_fail = ReservationLink(project='p', name='r-fail', zone='z')

  capacity, return_code = assess_available_slices(
      [res_link_fail],
      force_sub_block_targeting=False,
      system=cpu_system,
      vms_per_slice=cpu_system.vms_per_slice,
  )

  assert return_code == 1
  assert not capacity


@patch('xpk.core.capacity.project_id_to_project_number')
def test_assess_available_slices_aggregate_reservation_with_project_id(
    mock_project_id,
    commands_tester: CommandsTester,
    test_system: SystemCharacteristics,
):
  # Set the side_effect to raise an exception if called.
  # This ensures that the code does NOT try to resolve project number if it finds a match with project ID.
  mock_project_id.side_effect = Exception('Should not be called')

  project_id = 'my-project'
  zone = 'my-zone'
  accel_suffix = get_reservation_accelerator_type(test_system)
  target_type_with_id = (
      f'projects/{project_id}/zones/{zone}/acceleratorTypes/{accel_suffix}'
  )

  aggregate_payload = AggregateReservation(
      reserved_resources=[
          AcceleratorResource(
              accelerator_type=target_type_with_id, accelerator_count=100
          )
      ],
      in_use_resources=[],
  )
  setup_mock_reservation(
      commands_tester,
      aggregate_reservation=aggregate_payload,
  )
  res = ReservationLink(project=project_id, name='reservation', zone=zone)

  slices, return_code = assess_available_slices(
      [res],
      force_sub_block_targeting=False,
      system=test_system,
      vms_per_slice=test_system.vms_per_slice,
  )

  assert return_code == 0
  assert slices == [
      ReservationCapacity(
          res,
          available_slices=100,
      )
  ]
