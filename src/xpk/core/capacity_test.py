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
from unittest.mock import MagicMock, patch
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
)
from xpk.core.testing.commands_tester import CommandsTester


@pytest.fixture
def commands_tester(mocker):
  return CommandsTester(mocker)


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
):
  commands_tester.set_result_for_command(
      (0, 'count,in_use_count\n1,0'),
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
      [res], force_sub_block_targeting=False, required_hosts=1
  )

  assert slices == [ReservationCapacity(res, 1)]
  assert return_code == 0


def test_assess_available_slices_sub_block_unhealthy(
    commands_tester: CommandsTester,
):
  commands_tester.set_result_for_command(
      (0, ''), 'gcloud beta compute reservations sub-blocks list'
  )
  res = SubBlockReservationLink(
      project='project',
      name='reservation',
      zone='zone',
      block_name='block',
      sub_block_name='sub-block',
  )
  slices, return_code = assess_available_slices(
      [res], force_sub_block_targeting=False, required_hosts=1
  )

  assert not slices
  assert return_code == 0


def test_assess_available_slices_block_healthy(commands_tester: CommandsTester):
  # Mock 2 healthy sub-blocks
  commands_tester.set_result_for_command(
      (0, 'name,count,in_use_count\nsub1,1,0\nsub2,1,0'),
      'gcloud beta compute reservations sub-blocks list',
  )
  res = BlockReservationLink(
      project='project',
      name='reservation',
      zone='zone',
      block_name='block',
  )

  slices, return_code = assess_available_slices(
      [res], force_sub_block_targeting=True, required_hosts=1
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
):
  commands_tester.set_result_for_command(
      (0, ''), 'gcloud beta compute reservations sub-blocks list'
  )
  res = BlockReservationLink(
      project='project',
      name='reservation',
      zone='zone',
      block_name='block',
  )

  slices, return_code = assess_available_slices(
      [res], force_sub_block_targeting=True, required_hosts=1
  )

  assert not slices
  assert return_code == 0


def test_assess_available_slices_link_with_blocks(
    commands_tester: CommandsTester,
):
  commands_tester.set_result_for_command(
      (0, 'block1'), 'gcloud beta compute reservations blocks list'
  )
  commands_tester.set_result_for_command(
      (0, 'name,count,in_use_count\nsub1,1,0'),
      'gcloud beta compute reservations sub-blocks list',
      '--block-name=block1',
  )

  res = ReservationLink(project='project', name='reservation', zone='zone')
  slices, return_code = assess_available_slices(
      [res], force_sub_block_targeting=True, required_hosts=1
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
):
  commands_tester.set_result_for_command(
      (0, ''), 'gcloud beta compute reservations blocks list'
  )
  # Mock getting count
  commands_tester.set_result_for_command(
      (
          0,
          (
              '{"specificReservation": {"count": 2, "inUseCount": 0}, "status":'
              ' "READY"}'
          ),
      ),
      'gcloud beta compute reservations describe',
  )

  res = ReservationLink(project='project', name='reservation', zone='zone')
  slices, return_code = assess_available_slices(
      [res], force_sub_block_targeting=False, required_hosts=1
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
):
  commands_tester.set_result_for_command(
      (0, ''), 'gcloud beta compute reservations blocks list'
  )
  # Mock getting count
  commands_tester.set_result_for_command(
      (
          0,
          (
              '{"specificReservation": {"count": 2, "inUseCount": 0}, "status":'
              ' "READY"}'
          ),
      ),
      'gcloud beta compute reservations describe',
  )

  res = ReservationLink(project='project', name='reservation', zone='zone')
  slices, return_code = assess_available_slices(
      [res], force_sub_block_targeting=True, required_hosts=1
  )
  assert return_code == 0
  assert not slices


def test_assess_available_slices_host_filtering_insufficient_hosts(
    commands_tester: CommandsTester,
):
  # Mock a sub-block that has 14 free hosts but we need 16
  commands_tester.set_result_for_command(
      (0, 'count,in_use_count\n16,2'),
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
      [res], force_sub_block_targeting=False, required_hosts=16
  )

  assert not slices
  assert return_code == 0


def test_assess_available_slices_host_filtering_sufficient_hosts(
    commands_tester: CommandsTester,
):
  # Mock a reservation that has 46 free hosts, and we need 16 per slice.
  commands_tester.set_result_for_command(
      (
          0,
          (
              '{"specificReservation": {"count": 48, "inUseCount": 2},'
              ' "status": "READY"}'
          ),
      ),
      'gcloud beta compute reservations describe',
  )
  res_link = ReservationLink(project='p', name='r', zone='z')

  slices, return_code = assess_available_slices(
      [res_link], force_sub_block_targeting=False, required_hosts=16
  )

  assert return_code == 0
  assert slices == [
      ReservationCapacity(
          ReservationLink(project='p', name='r', zone='z'), available_slices=2
      )
  ]


def test_assess_available_slices_aggregate_reservation(
    commands_tester: CommandsTester,
):
  json_output = """
  {
      "aggregateReservation": {
          "reservedResources": [
              {
                  "accelerator": {
                      "acceleratorType": "accelerator-1",
                      "acceleratorCount": 100
                  }
              }
          ],
          "inUseResources": [
              {
                  "accelerator": {
                      "acceleratorType": "accelerator-1",
                      "acceleratorCount": 20
                  }
              },
              {
                  "accelerator": {
                      "acceleratorType": "accelerator-2",
                      "acceleratorCount": 50
                  }
              }
          ]
      },
      "status": "READY"
  }
  """
  commands_tester.set_result_for_command(
      (0, json_output),
      'gcloud beta compute reservations describe',
  )
  res = ReservationLink(project='project', name='reservation', zone='zone')

  slices, return_code = assess_available_slices(
      [res], force_sub_block_targeting=False, required_hosts=1
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
):
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
      [res_sub], force_sub_block_targeting=False, required_hosts=1
  )

  assert not slices
  assert return_code == 1


def test_assess_available_slices_failures_block_sub_blocks_check(
    commands_tester: CommandsTester,
):
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
      [res_block], force_sub_block_targeting=True, required_hosts=1
  )

  assert not slices
  assert return_code == 1


def test_assess_available_slices_failures_reservation_blocks_check(
    commands_tester: CommandsTester,
):
  res = ReservationLink(project='project', name='reservation', zone='zone')
  commands_tester.set_result_for_command(
      (1, ''), 'gcloud beta compute reservations blocks list'
  )

  slices, return_code = assess_available_slices(
      [res], force_sub_block_targeting=True, required_hosts=1
  )

  assert not slices
  assert return_code == 1


def test_assess_available_slices_failures_reservation_count_check(
    commands_tester: CommandsTester,
):
  res = ReservationLink(project='project', name='reservation', zone='zone')
  commands_tester.set_result_for_command(
      (1, ''), 'gcloud beta compute reservations describe'
  )

  slices, return_code = assess_available_slices(
      [res], force_sub_block_targeting=False, required_hosts=1
  )

  assert not slices
  assert return_code == 1


def test_assess_available_slices_mixed_reservations_with_subblock_targeting(
    commands_tester: CommandsTester,
):
  # Mock block reservation with 2 healthy sub-blocks
  block_res = BlockReservationLink(
      project='project', name='res1', zone='zone', block_name='block1'
  )
  commands_tester.set_result_for_command(
      (0, 'name,count,in_use_count\nsub1,1,0\nsub2,1,0'),
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
      (0, 'count,in_use_count\n1,0'),
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
      (0, ''),
      'gcloud beta compute reservations sub-blocks list res3',
      '--filter="name=sub4 AND healthInfo.healthStatus=HEALTHY"',
  )

  slices, return_code = assess_available_slices(
      [block_res, sub_res_healthy, sub_res_unhealthy],
      force_sub_block_targeting=True,
      required_hosts=1,
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


def test_assess_available_slices_deduplicates(commands_tester: CommandsTester):
  block_res = BlockReservationLink(
      project='project', name='res1', zone='zone', block_name='block1'
  )
  sub_block_name = 'sub1'
  commands_tester.set_result_for_command(
      (0, f'name,count,in_use_count\n{sub_block_name},1,0'),
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
      (0, 'count,in_use_count\n1,0'),
      'gcloud beta compute reservations sub-blocks list res1',
      '--block-name=block1',
      f'--filter="name={sub_block_name}',
  )

  slices, return_code = assess_available_slices(
      [block_res, sub_res],
      force_sub_block_targeting=True,
      required_hosts=1,
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
