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
import sys
from unittest.mock import MagicMock, patch

# Mock google.cloud.resourcemanager_v3 before importing capacity
sys.modules['google.cloud.resourcemanager_v3'] = MagicMock()

from .capacity import (
    get_capacity_type,
    CapacityType,
    assess_available_slices,
    ReservationLink,
    BlockReservationLink,
    SubBlockReservationLink,
    ReservationCapacity,
    _parse_reservation_sub_block,
)
from .reservation import (
    get_reservation_cached,
)
from xpk.core.testing.commands_tester import CommandsTester
from .system_characteristics import SystemCharacteristics, AcceleratorType, DockerPlatform, GpuConfig


@pytest.fixture
def commands_tester(mocker):
  return CommandsTester(mocker)


@pytest.fixture(autouse=True)
def clear_capacity_cache():
  get_reservation_cached.cache_clear()
  yield
  get_reservation_cached.cache_clear()


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


def test_assess_available_slices_sub_block_healthy(
    commands_tester: CommandsTester,
    test_system: SystemCharacteristics,
):
  commands_tester.set_result_for_command(
      (
          0,
          (
              '{"specificReservation": {"count": 48, "inUseCount": 2,'
              ' "instanceProperties": {"machineType": "test-machine"}},'
              ' "status": "READY"}'
          ),
      ),
      'gcloud beta compute reservations describe',
  )
  commands_tester.set_result_for_command(
      (0, '[{"count": 1, "inUseCount": 0}]'),
      'gcloud beta compute reservations sub-blocks list',
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
      required_hosts=1,
      system=test_system,
  )

  assert slices == [ReservationCapacity(res, 1)]
  assert return_code == 0


def test_assess_available_slices_sub_block_unhealthy(
    commands_tester: CommandsTester,
    test_system: SystemCharacteristics,
):
  commands_tester.set_result_for_command(
      (
          0,
          (
              '{"specificReservation": {"count": 48, "inUseCount": 2,'
              ' "instanceProperties": {"machineType": "test-machine"}},'
              ' "status": "READY"}'
          ),
      ),
      'gcloud beta compute reservations describe',
  )
  commands_tester.set_result_for_command(
      (0, '[]'), 'gcloud beta compute reservations sub-blocks list'
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
      required_hosts=1,
      system=test_system,
  )

  assert not slices
  assert return_code == 0


def test_assess_available_slices_block_healthy(
    commands_tester: CommandsTester, test_system: SystemCharacteristics
):
  # Mock describe
  commands_tester.set_result_for_command(
      (
          0,
          (
              '{"specificReservation": {"count": 48, "inUseCount": 2,'
              ' "instanceProperties": {"machineType": "test-machine"}},'
              ' "status": "READY"}'
          ),
      ),
      'gcloud beta compute reservations describe',
  )
  # Mock 2 healthy sub-blocks
  commands_tester.set_result_for_command(
      (
          0,
          (
              '[{"name": "sub1", "count": 1, "inUseCount": 0}, {"name":'
              ' "sub2", "count": 1, "inUseCount": 0}]'
          ),
      ),
      'gcloud beta compute reservations sub-blocks list',
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
      required_hosts=1,
      system=test_system,
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
          available_slices=1,
      ),
  ]


def test_assess_available_slices_block_unhealthy(
    commands_tester: CommandsTester,
    test_system: SystemCharacteristics,
):
  commands_tester.set_result_for_command(
      (
          0,
          (
              '{"specificReservation": {"count": 48, "inUseCount": 2,'
              ' "instanceProperties": {"machineType": "test-machine"}},'
              ' "status": "READY"}'
          ),
      ),
      'gcloud beta compute reservations describe',
  )
  commands_tester.set_result_for_command(
      (0, '[]'), 'gcloud beta compute reservations sub-blocks list'
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
      required_hosts=1,
      system=test_system,
  )

  assert not slices
  assert return_code == 0


def test_assess_available_slices_link_with_blocks(
    commands_tester: CommandsTester,
    test_system: SystemCharacteristics,
):
  commands_tester.set_result_for_command(
      (
          0,
          (
              '{"specificReservation": {"count": 48, "inUseCount": 2,'
              ' "instanceProperties": {"machineType": "test-machine"}},'
              ' "status": "READY"}'
          ),
      ),
      'gcloud beta compute reservations describe',
  )
  commands_tester.set_result_for_command(
      (0, 'block1'), 'gcloud beta compute reservations blocks list'
  )
  commands_tester.set_result_for_command(
      (0, '[{"name": "sub1", "count": 1, "inUseCount": 0}]'),
      'gcloud beta compute reservations sub-blocks list',
      '--block-name=block1',
  )

  res = ReservationLink(project='project', name='reservation', zone='zone')
  slices, return_code = assess_available_slices(
      [res],
      force_sub_block_targeting=True,
      required_hosts=1,
      system=test_system,
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


def test_assess_available_slices_link_without_blocks(
    commands_tester: CommandsTester,
    test_system: SystemCharacteristics,
):
  commands_tester.set_result_for_command(
      (0, ''), 'gcloud beta compute reservations blocks list'
  )
  # Mock getting count
  commands_tester.set_result_for_command(
      (
          0,
          (
              '{"specificReservation": {"count": 2, "inUseCount": 0,'
              ' "instanceProperties": {"machineType": "test-machine"}},'
              ' "status": "READY"}'
          ),
      ),
      'gcloud beta compute reservations describe',
  )

  res = ReservationLink(project='project', name='reservation', zone='zone')
  slices, return_code = assess_available_slices(
      [res],
      force_sub_block_targeting=False,
      required_hosts=1,
      system=test_system,
  )
  assert return_code == 0
  assert slices == [
      ReservationCapacity(
          ReservationLink(project='project', name='reservation', zone='zone'),
          available_slices=2,
      )
  ]


def test_assess_available_slices_link_without_blocks_sub_block_targeting(
    commands_tester: CommandsTester,
    test_system: SystemCharacteristics,
):
  commands_tester.set_result_for_command(
      (0, ''), 'gcloud beta compute reservations blocks list'
  )
  # Mock getting count
  commands_tester.set_result_for_command(
      (
          0,
          (
              '{"specificReservation": {"count": 2, "inUseCount": 0,'
              ' "instanceProperties": {"machineType": "test-machine"}},'
              ' "status": "READY"}'
          ),
      ),
      'gcloud beta compute reservations describe',
  )

  res = ReservationLink(project='project', name='reservation', zone='zone')
  slices, return_code = assess_available_slices(
      [res],
      force_sub_block_targeting=True,
      required_hosts=1,
      system=test_system,
  )
  assert return_code == 0
  assert not slices


def test_assess_available_slices_host_filtering_insufficient_hosts(
    commands_tester: CommandsTester,
    test_system: SystemCharacteristics,
):
  # Mock a sub-block that has 14 free hosts but we need 16
  commands_tester.set_result_for_command(
      (0, '[{"count": 16, "inUseCount": 2}]'),
      'gcloud beta compute reservations sub-blocks list',
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
      required_hosts=16,
      system=test_system,
  )

  assert not slices
  assert return_code == 0


def test_assess_available_slices_host_filtering_sufficient_hosts(
    commands_tester: CommandsTester,
    test_system: SystemCharacteristics,
):
  # Mock a reservation that has 46 free hosts, and we need 16 per slice.
  commands_tester.set_result_for_command(
      (
          0,
          (
              '{"specificReservation": {"count": 48, "inUseCount": 2,'
              ' "instanceProperties": {"machineType": "test-machine"}},'
              ' "status": "READY"}'
          ),
      ),
      'gcloud beta compute reservations describe',
  )
  res_link = ReservationLink(project='p', name='r', zone='z')

  slices, return_code = assess_available_slices(
      [res_link],
      force_sub_block_targeting=False,
      required_hosts=16,
      system=test_system,
  )

  assert return_code == 0
  assert slices == [
      ReservationCapacity(
          ReservationLink(project='p', name='r', zone='z'), available_slices=2
      )
  ]


@patch('xpk.core.capacity.project_id_to_project_number', return_value='12345')
def test_assess_available_slices_aggregate_reservation(
    mock_project_id,
    commands_tester: CommandsTester,
    test_system: SystemCharacteristics,
):
  # For TPU, target type includes project number and zone
  target_type = f'projects/12345/zones/zone/acceleratorTypes/{test_system.reservation_accelerator_type}'
  json_output = f"""
  {{
      "aggregateReservation": {{
          "reservedResources": [
              {{
                  "accelerator": {{
                      "acceleratorType": "{target_type}",
                      "acceleratorCount": 100
                  }}
              }},
              {{
                  "accelerator": {{
                      "acceleratorType": "wrong-type",
                      "acceleratorCount": 100
                  }}
              }}
          ],
          "inUseResources": [
              {{
                  "accelerator": {{
                      "acceleratorType": "{target_type}",
                      "acceleratorCount": 20
                  }}
              }},
              {{
                  "accelerator": {{
                      "acceleratorType": "accelerator-2",
                      "acceleratorCount": 50
                  }}
              }}
          ]
      }},
      "status": "READY"
  }}
  """
  commands_tester.set_result_for_command(
      (0, json_output),
      'gcloud beta compute reservations describe',
  )
  res = ReservationLink(project='project', name='reservation', zone='zone')

  slices, return_code = assess_available_slices(
      [res],
      force_sub_block_targeting=False,
      required_hosts=1,
      system=test_system,
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
  commands_tester.set_result_for_command(
      (
          0,
          (
              '{"specificReservation": {"count": 100, "inUseCount": 0,'
              ' "instanceProperties": {"machineType": "test-machine"}},'
              ' "status": "READY"}'
          ),
      ),
      'gcloud beta compute reservations describe',
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
      required_hosts=1,
      system=test_system,
  )

  assert not slices
  assert return_code == 0


def test_assess_available_slices_failures_block_sub_blocks_check(
    commands_tester: CommandsTester,
    test_system: SystemCharacteristics,
):
  commands_tester.set_result_for_command(
      (
          0,
          (
              '{"specificReservation": {"count": 100, "inUseCount": 0,'
              ' "instanceProperties": {"machineType": "test-machine"}},'
              ' "status": "READY"}'
          ),
      ),
      'gcloud beta compute reservations describe',
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
      required_hosts=1,
      system=test_system,
  )

  assert not slices
  assert return_code == 0


def test_assess_available_slices_failures_reservation_blocks_check(
    commands_tester: CommandsTester,
    test_system: SystemCharacteristics,
):
  commands_tester.set_result_for_command(
      (
          0,
          (
              '{"specificReservation": {"count": 100, "inUseCount": 0,'
              ' "instanceProperties": {"machineType": "test-machine"}},'
              ' "status": "READY"}'
          ),
      ),
      'gcloud beta compute reservations describe',
  )
  res = ReservationLink(project='project', name='reservation', zone='zone')
  commands_tester.set_result_for_command(
      (1, ''), 'gcloud beta compute reservations blocks list'
  )

  slices, return_code = assess_available_slices(
      [res],
      force_sub_block_targeting=True,
      required_hosts=1,
      system=test_system,
  )

  assert not slices
  assert return_code == 0


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
      required_hosts=1,
      system=test_system,
  )

  assert not slices
  assert return_code == 0


def test_assess_available_slices_mixed_reservations_with_subblock_targeting(
    commands_tester: CommandsTester,
    test_system: SystemCharacteristics,
):
  # Mock describe for all reservations
  commands_tester.set_result_for_command(
      (
          0,
          (
              '{"specificReservation": {"count": 48, "inUseCount": 2,'
              ' "instanceProperties": {"machineType": "test-machine"}},'
              ' "status": "READY"}'
          ),
      ),
      'gcloud beta compute reservations describe',
  )

  # Mock block reservation with 2 healthy sub-blocks

  block_res = BlockReservationLink(
      project='project', name='res1', zone='zone', block_name='block1'
  )
  commands_tester.set_result_for_command(
      (
          0,
          (
              '[{"name": "sub1", "count": 1, "inUseCount": 0}, {"name":'
              ' "sub2", "count": 1, "inUseCount": 0}]'
          ),
      ),
      'gcloud beta compute reservations sub-blocks list res1',
      '--block-name=block1',
  )

  # Mock healthy sub-block reservation
  sub_res_healthy = SubBlockReservationLink(
      project='project',
      name='res2',
      zone='zone',
      block_name='block2',
      sub_block_name='sub3',
  )
  commands_tester.set_result_for_command(
      (0, '[{"count": 1, "inUseCount": 0}]'),
      'gcloud beta compute reservations sub-blocks list res2',
      '--filter="name=sub3 AND healthInfo.healthStatus=HEALTHY"',
  )

  # Mock unhealthy sub-block reservation
  sub_res_unhealthy = SubBlockReservationLink(
      project='project',
      name='res3',
      zone='zone',
      block_name='block3',
      sub_block_name='sub4',
  )
  commands_tester.set_result_for_command(
      (0, '[]'),
      'gcloud beta compute reservations sub-blocks list res3',
      '--filter="name=sub4 AND healthInfo.healthStatus=HEALTHY"',
  )

  slices, return_code = assess_available_slices(
      [block_res, sub_res_healthy, sub_res_unhealthy],
      force_sub_block_targeting=True,
      required_hosts=1,
      system=test_system,
  )

  assert return_code == 0
  assert slices == [
      ReservationCapacity(
          SubBlockReservationLink(
              project='project',
              name='res1',
              zone='zone',
              block_name='block1',
              sub_block_name='sub1',
          ),
          available_slices=1,
      ),
      ReservationCapacity(
          SubBlockReservationLink(
              project='project',
              name='res1',
              zone='zone',
              block_name='block1',
              sub_block_name='sub2',
          ),
          available_slices=1,
      ),
      ReservationCapacity(
          sub_res_healthy,
          available_slices=1,
      ),
  ]


def test_assess_available_slices_deduplicates(
    commands_tester: CommandsTester, test_system: SystemCharacteristics
):
  # Mock describe
  commands_tester.set_result_for_command(
      (
          0,
          (
              '{"specificReservation": {"count": 48, "inUseCount": 2,'
              ' "instanceProperties": {"machineType": "test-machine"}},'
              ' "status": "READY"}'
          ),
      ),
      'gcloud beta compute reservations describe',
  )

  block_res = BlockReservationLink(
      project='project', name='res1', zone='zone', block_name='block1'
  )
  sub_block_name = 'sub1'
  commands_tester.set_result_for_command(
      (0, f'[{{"name": "{sub_block_name}", "count": 1, "inUseCount": 0}}]'),
      'gcloud beta compute reservations sub-blocks list res1',
      '--block-name=block1',
  )
  sub_res = SubBlockReservationLink(
      project='project',
      name='res1',
      zone='zone',
      block_name='block1',
      sub_block_name=sub_block_name,
  )
  commands_tester.set_result_for_command(
      (0, '[{"count": 1, "inUseCount": 0}]'),
      'gcloud beta compute reservations sub-blocks list res1',
      '--block-name=block1',
      f'--filter="name={sub_block_name}',
  )

  slices, return_code = assess_available_slices(
      [block_res, sub_res],
      force_sub_block_targeting=True,
      required_hosts=1,
      system=test_system,
  )

  assert return_code == 0
  assert slices == [
      ReservationCapacity(
          SubBlockReservationLink(
              project='project',
              name='res1',
              zone='zone',
              block_name='block1',
              sub_block_name='sub1',
          ),
          available_slices=1,
      )
  ]


def test_parse_reservation_sub_block():
  data = {'name': 'sub1', 'count': 10, 'inUseCount': 2}
  res = _parse_reservation_sub_block(data)
  assert res.name == 'sub1'
  assert res.count == 10
  assert res.in_use_count == 2


def test_parse_reservation_sub_block_defaults():
  data = {}
  res = _parse_reservation_sub_block(data)
  assert res.name == ''
  assert res.count == 0
  assert res.in_use_count == 0


def test_get_reservation_count_validates_tpu_machine_type(
    commands_tester: CommandsTester, test_system: SystemCharacteristics
):
  # Success case: matches
  commands_tester.set_result_for_command(
      (
          0,
          (
              '{"specificReservation": {"count": 10, "inUseCount": 2,'
              ' "instanceProperties": {"machineType": "test-machine"}},'
              ' "status": "READY"}'
          ),
      ),
      'gcloud beta compute reservations describe',
  )
  res_link = ReservationLink(project='p', name='r', zone='z')
  count, return_code = assess_available_slices(
      [res_link],
      force_sub_block_targeting=False,
      required_hosts=1,
      system=test_system,
  )
  assert return_code == 0
  assert count[0].available_slices == 8

  # Failure case: mismatch
  commands_tester.set_result_for_command(
      (
          0,
          (
              '{"specificReservation": {"count": 10, "inUseCount": 2,'
              ' "instanceProperties": {"machineType": "wrong-machine"}},'
              ' "status": "READY"}'
          ),
      ),
      'gcloud beta compute reservations describe',
  )
  res_link_fail = ReservationLink(project='p', name='r-fail', zone='z')
  count, return_code = assess_available_slices(
      [res_link_fail],
      force_sub_block_targeting=False,
      required_hosts=1,
      system=test_system,
  )
  assert return_code == 0
  assert not count


def test_get_reservation_count_validates_gpu_accelerator_type(
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

  # Success case: matches
  commands_tester.set_result_for_command(
      (
          0,
          (
              '{"specificReservation": {"count": 10, "inUseCount": 2,'
              ' "instanceProperties": {"guestAccelerators":'
              ' [{"acceleratorType": "nvidia-test"}]}}, "status": "READY"}'
          ),
      ),
      'gcloud beta compute reservations describe',
  )
  res_link = ReservationLink(project='p', name='r', zone='z')
  count, return_code = assess_available_slices(
      [res_link],
      force_sub_block_targeting=False,
      required_hosts=1,
      system=gpu_system,
  )
  assert return_code == 0
  assert count[0].available_slices == 8

  # Failure case: mismatch
  commands_tester.set_result_for_command(
      (
          0,
          (
              '{"specificReservation": {"count": 10, "inUseCount": 2,'
              ' "instanceProperties": {"guestAccelerators":'
              ' [{"acceleratorType": "nvidia-wrong"}]}}, "status": "READY"}'
          ),
      ),
      'gcloud beta compute reservations describe',
  )
  res_link_fail = ReservationLink(project='p', name='r-fail', zone='z')
  count, return_code = assess_available_slices(
      [res_link_fail],
      force_sub_block_targeting=False,
      required_hosts=1,
      system=gpu_system,
  )
  assert return_code == 0
  assert not count
