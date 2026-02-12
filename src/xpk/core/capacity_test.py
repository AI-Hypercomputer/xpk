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
    get_reservation_deployment_type,
    parse_reservation,
    get_capacity_type,
    CapacityType,
    verify_reservations_exist,
    get_reservations_list,
    assess_available_slices,
    to_reservation_path,
    ReservationLink,
    BlockReservationLink,
    SubBlockReservationLink,
    ReservationCapacity,
    _parse_reservation,
    _parse_reservation_sub_block,
    _SpecificReservation,
    _AcceleratorResource,
    _verify_reservation_configuration,
    _Reservation,
    _get_reservation_cached,
)
from xpk.core.testing.commands_tester import CommandsTester
from .system_characteristics import SystemCharacteristics, AcceleratorType, DockerPlatform, GpuConfig


@pytest.fixture
def commands_tester(mocker):
  return CommandsTester(mocker)


@pytest.fixture(autouse=True)
def clear_capacity_cache():
  _get_reservation_cached.cache_clear()
  yield
  _get_reservation_cached.cache_clear()


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


@patch('xpk.core.capacity.xpk_print')
def test_get_reservation_deployment_type_exits_with_command_fails(
    xpk_print: MagicMock, mocker
):
  mocker.patch(
      target='xpk.core.capacity.run_command_for_value', return_value=(1, '')
  )
  with pytest.raises(SystemExit):
    get_reservation_deployment_type(
        reservation=ReservationLink(
            project='project', name='reservation', zone='zone'
        ),
    )

  assert (
      'Get reservation deployment type ERROR 1'
      in xpk_print.mock_calls[0].args[0]
  )


def test_get_reservation_deployment_type_returns_deployment_type_when_command_succeeds(
    mocker,
):
  mocker.patch(
      target='xpk.core.capacity.run_command_for_value',
      return_value=(0, 'DENSE'),
  )
  result = get_reservation_deployment_type(
      reservation=ReservationLink(
          project='project', name='reservation', zone='zone'
      ),
  )
  assert result == 'DENSE'


@pytest.mark.parametrize(
    argnames='reservation_path,expected_reservation',
    argvalues=[
        (
            'reservation',
            ReservationLink(
                project='cluster-project', name='reservation', zone='zone'
            ),
        ),
        (
            'reservation/reservationBlocks/block',
            BlockReservationLink(
                project='cluster-project',
                name='reservation',
                zone='zone',
                block_name='block',
            ),
        ),
        (
            'reservation/reservationBlocks/block/reservationSubBlocks/subblock',
            SubBlockReservationLink(
                project='cluster-project',
                name='reservation',
                zone='zone',
                block_name='block',
                sub_block_name='subblock',
            ),
        ),
        (
            'projects/project/reservations/reservation',
            ReservationLink(project='project', name='reservation', zone='zone'),
        ),
        (
            'projects/project/reservations/reservation/reservationBlocks/block',
            BlockReservationLink(
                project='project',
                name='reservation',
                zone='zone',
                block_name='block',
            ),
        ),
        (
            'projects/project/reservations/reservation/reservationBlocks/block/reservationSubBlocks/subblock',
            SubBlockReservationLink(
                project='project',
                name='reservation',
                zone='zone',
                block_name='block',
                sub_block_name='subblock',
            ),
        ),
    ],
)
def test_parse_reservation_parses_valid_reservations(
    reservation_path: str,
    expected_reservation: ReservationLink,
):
  actual_reservation = parse_reservation(
      reservation_path, 'cluster-project', 'zone'
  )

  assert actual_reservation == expected_reservation


def test_to_reservation_path_for_reservation():
  res = ReservationLink(project='project', name='reservation', zone='zone')
  assert to_reservation_path(res, 'project') == 'reservation'
  assert (
      to_reservation_path(res, 'other-project')
      == 'projects/project/reservations/reservation'
  )


def test_to_reservation_path_for_block_reservation():
  res_block = BlockReservationLink(
      project='project', name='reservation', zone='zone', block_name='block'
  )
  assert (
      to_reservation_path(res_block, 'project')
      == 'reservation/reservationBlocks/block'
  )
  assert (
      to_reservation_path(res_block, 'other-project')
      == 'projects/project/reservations/reservation/reservationBlocks/block'
  )


def test_to_reservation_path_for_sub_block_reservation():
  res_sub = SubBlockReservationLink(
      project='project',
      name='reservation',
      zone='zone',
      block_name='block',
      sub_block_name='subblock',
  )
  assert (
      to_reservation_path(res_sub, 'project')
      == 'reservation/reservationBlocks/block/reservationSubBlocks/subblock'
  )
  assert (
      to_reservation_path(res_sub, 'other-project')
      == 'projects/project/reservations/reservation/reservationBlocks/block/reservationSubBlocks/subblock'
  )


@pytest.mark.parametrize(
    argnames='reservation_path',
    argvalues=[
        '',
        '/name',
        'name/',
        'name/reservationBlocks/',
        'name/reservationBlocks/block/reservationSubBlocks/',
        'name/reservationBlocks/block/reservationSubBlocks/subblock/extra',
        'name/reservationBlock/block/reservationSubBlocks/subblock',
        'name/reservationBlocks/block/reservationSubBlock/subblock',
        'reservations/name',
        'project/project/reservations/name',
        'projects/project/reservation/name',
        'projects/project/reservations',
        'projects/project/reservations/name/reservationBlocks/block/reservationSubBlocks/subblock/extra',
        'projects/project/reservations/name/reservationBlocks//reservationSubBlocks/subblock',
    ],
)
@patch('xpk.core.capacity.xpk_print')
def test_parse_reservation_fails_on_invalid_reservations(
    xpk_print: MagicMock, reservation_path: str
):
  with pytest.raises(SystemExit):
    parse_reservation(reservation_path, 'cluster-project', 'zone')

  assert 'Unable to parse reservation' in xpk_print.mock_calls[0].args[0]


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


@patch('xpk.core.capacity.run_command_with_updates', return_value=0)
def test_verify_reservations_exist_multiple(mock_run, mocker):
  args = mocker.Mock(reservation='res1,res2', project='project', zone='zone')

  assert verify_reservations_exist(args) == 0
  assert mock_run.call_count == 2


def test_get_reservations_list_with_single_reservation(mocker):
  args = mocker.Mock(reservation='res1', project='project', zone='zone')
  assert get_reservations_list(args) == [
      ReservationLink(project='project', name='res1', zone='zone')
  ]


def test_get_reservations_list_with_multiple_reservations(mocker):
  args = mocker.Mock(reservation='res1,res2', project='project', zone='zone')
  assert get_reservations_list(args) == [
      ReservationLink(project='project', name='res1', zone='zone'),
      ReservationLink(project='project', name='res2', zone='zone'),
  ]


def test_get_reservations_list_with_whitespace(mocker):
  args = mocker.Mock(reservation='res1, res2 ', project='project', zone='zone')
  assert get_reservations_list(args) == [
      ReservationLink(project='project', name='res1', zone='zone'),
      ReservationLink(project='project', name='res2', zone='zone'),
  ]


def test_get_reservations_list_none(mocker):
  args = mocker.Mock(reservation=None)
  assert get_reservations_list(args) == []


def test_get_reservations_list_empty(mocker):
  args = mocker.Mock(reservation='')
  assert get_reservations_list(args) == []


def test_to_reservation_path_sub_block():
  res = SubBlockReservationLink(
      project='project',
      name='reservation',
      zone='zone',
      block_name='block',
      sub_block_name='sub-block',
  )
  assert (
      to_reservation_path(res, 'project')
      == 'reservation/reservationBlocks/block/reservationSubBlocks/sub-block'
  )


def test_to_reservation_path_block():
  res_block = BlockReservationLink(
      project='project',
      name='reservation',
      zone='zone',
      block_name='block',
  )
  assert (
      to_reservation_path(res_block, 'project')
      == 'reservation/reservationBlocks/block'
  )


def test_to_reservation_path_reservation():
  res_simple = ReservationLink(
      project='project', name='reservation', zone='zone'
  )
  assert to_reservation_path(res_simple, 'project') == 'reservation'


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


def test_parse_specific_reservation():
  data = {
      'specificReservation': {
          'count': '10',
          'inUseCount': '2',
          'instanceProperties': {
              'machineType': 'test-machine',
              'guestAccelerators': [{
                  'acceleratorCount': 1,
                  'acceleratorType': 'nvidia-test',
              }],
          },
      },
      'status': 'READY',
  }
  res = _parse_reservation('res1', data)
  assert res.name == 'res1'
  assert res.specificReservation == _SpecificReservation(
      count=10,
      inUseCount=2,
      machine_type='test-machine',
      guest_accelerators=[
          _AcceleratorResource(
              acceleratorCount=1, acceleratorType='nvidia-test'
          )
      ],
  )
  assert res.aggregateReservation is None


def test_parse_specific_reservation_defaults():
  data = {'specificReservation': {}, 'status': 'READY'}
  res = _parse_reservation('res1', data)
  assert res.specificReservation == _SpecificReservation(
      count=0, inUseCount=0, machine_type='', guest_accelerators=[]
  )


def test_parse_aggregate_reservation():
  data = {
      'aggregateReservation': {
          'reservedResources': [{
              'accelerator': {
                  'acceleratorCount': 100,
                  'acceleratorType': 'tpu',
              }
          }],
          'inUseResources': [{
              'accelerator': {
                  'acceleratorCount': 20,
                  'acceleratorType': 'tpu',
              }
          }],
      },
      'status': 'READY',
  }
  res = _parse_reservation('res1', data)
  assert res.aggregateReservation is not None
  assert len(res.aggregateReservation.reservedResources) == 1
  assert res.aggregateReservation.reservedResources[0] == _AcceleratorResource(
      acceleratorCount=100, acceleratorType='tpu'
  )
  assert len(res.aggregateReservation.inUseResources) == 1
  assert res.aggregateReservation.inUseResources[0] == _AcceleratorResource(
      acceleratorCount=20, acceleratorType='tpu'
  )


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


@patch('xpk.core.capacity.xpk_print')
def test_verify_reservation_configuration(xpk_print: MagicMock):
  # 1. Valid TPU
  valid_tpu_system = SystemCharacteristics(
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
  valid_tpu_reservation = _Reservation(
      name='res1',
      specificReservation=_SpecificReservation(
          count=10,
          inUseCount=0,
          machine_type='test-machine',
          guest_accelerators=[],
      ),
      aggregateReservation=None,
  )
  assert _verify_reservation_configuration(
      valid_tpu_reservation, valid_tpu_system
  )

  # 2. Invalid TPU (machine type mismatch)
  invalid_tpu_reservation = _Reservation(
      name='res1',
      specificReservation=_SpecificReservation(
          count=10,
          inUseCount=0,
          machine_type='wrong-machine',
          guest_accelerators=[],
      ),
      aggregateReservation=None,
  )
  assert not _verify_reservation_configuration(
      invalid_tpu_reservation, valid_tpu_system
  )
  assert 'ERROR: Reservation' in xpk_print.call_args[0][0]

  # 3. Valid GPU
  valid_gpu_system = SystemCharacteristics(
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
  valid_gpu_reservation = _Reservation(
      name='res2',
      specificReservation=_SpecificReservation(
          count=10,
          inUseCount=0,
          machine_type='g2-standard-12',
          guest_accelerators=[
              _AcceleratorResource(
                  acceleratorCount=1, acceleratorType='nvidia-test'
              )
          ],
      ),
      aggregateReservation=None,
  )
  assert _verify_reservation_configuration(
      valid_gpu_reservation, valid_gpu_system
  )

  # 4. Invalid GPU (accelerator type mismatch)
  invalid_gpu_reservation = _Reservation(
      name='res2',
      specificReservation=_SpecificReservation(
          count=10,
          inUseCount=0,
          machine_type='g2-standard-12',
          guest_accelerators=[
              _AcceleratorResource(
                  acceleratorCount=1, acceleratorType='nvidia-wrong'
              )
          ],
      ),
      aggregateReservation=None,
  )
  assert not _verify_reservation_configuration(
      invalid_gpu_reservation, valid_gpu_system
  )
  assert 'ERROR: Reservation' in xpk_print.call_args[0][0]

  # 5. No specific reservation (should pass)
  no_specific_reservation = _Reservation(
      name='res3', specificReservation=None, aggregateReservation=None
  )
  assert _verify_reservation_configuration(
      no_specific_reservation, valid_tpu_system
  )


def test_get_reservation_cached_caching(mocker):
  mock_run_command = mocker.patch(
      'xpk.core.capacity.run_command_for_value',
      return_value=(0, '{"name": "res", "status": "READY"}'),
  )

  # First call
  _get_reservation_cached('project', 'zone', 'res1')
  assert mock_run_command.call_count == 1

  # Second call with same args
  _get_reservation_cached('project', 'zone', 'res1')
  assert mock_run_command.call_count == 1  # Should still be 1

  # Third call with different args
  _get_reservation_cached('project', 'zone', 'res2')
  assert mock_run_command.call_count == 2


def test_assess_available_slices_filters_invalid_block_reservation(
    commands_tester: CommandsTester,
    test_system: SystemCharacteristics,
):
  # Mock the parent reservation being fetched, but with invalid machine type
  commands_tester.set_result_for_command(
      (
          0,
          (
              '{"specificReservation": {"count": 100, "inUseCount": 0,'
              ' "instanceProperties": {"machineType": "wrong-machine"}},'
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

  slices, return_code = assess_available_slices(
      [res_block],
      force_sub_block_targeting=True,
      required_hosts=1,
      system=test_system,
  )

  # Should return empty because validation failed
  assert not slices
  assert return_code == 0
