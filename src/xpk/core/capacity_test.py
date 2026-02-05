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
    get_capacity_node_selectors_from_capacity_type,
)
from xpk.core.testing.commands_tester import CommandsTester


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
            'projects/p/reservations/reservation',
            ReservationLink(project='p', name='reservation', zone='zone'),
        ),
        (
            'projects/p/reservations/reservation/reservationBlocks/block',
            BlockReservationLink(
                project='p',
                name='reservation',
                zone='zone',
                block_name='block',
            ),
        ),
        (
            'projects/p/reservations/reservation/reservationBlocks/block/reservationSubBlocks/subblock',
            SubBlockReservationLink(
                project='p',
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
        'project/p/reservations/name',
        'projects/p/reservation/name',
        'projects/p/reservations',
        'projects/p/reservations/name/reservationBlocks/block/reservationSubBlocks/subblock/extra',
        'projects/p/reservations/name/reservationBlocks//reservationSubBlocks/subblock',
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
  args = MagicMock()
  args.on_demand = False
  args.spot = False
  args.flex = False
  args.reservation = 'res1,res2'
  args.project = 'test-project'
  args.zone = 'us-central1-a'
  mocker.patch('xpk.core.capacity.run_command_with_updates', return_value=0)

  capacity_type, return_code = get_capacity_type(args)

  assert capacity_type == CapacityType.RESERVATION
  assert return_code == 0


def test_verify_reservations_exist_multiple(mocker):
  args = MagicMock()
  args.reservation = 'res1,res2'
  args.project = 'test-project'
  args.zone = 'us-central1-a'

  mock_run = mocker.patch(
      'xpk.core.capacity.run_command_with_updates', return_value=0
  )

  return_code = verify_reservations_exist(args)

  assert return_code == 0
  assert mock_run.call_count == 2


def test_get_reservations_list_with_single_reservation(mocker):
  args = mocker.Mock(
      reservation='res1', project='project', zone='us-central1-a'
  )
  assert get_reservations_list(args) == [
      ReservationLink(project='project', name='res1', zone='us-central1-a')
  ]


def test_get_reservations_list_with_multiple_reservations(mocker):
  args = mocker.Mock(
      reservation='res1,res2', project='project', zone='us-central1-a'
  )
  assert get_reservations_list(args) == [
      ReservationLink(project='project', name='res1', zone='us-central1-a'),
      ReservationLink(project='project', name='res2', zone='us-central1-a'),
  ]


def test_get_reservations_list_with_whitespace(mocker):
  args = mocker.Mock(
      reservation='res1, res2 ', project='project', zone='us-central1-a'
  )
  assert get_reservations_list(args) == [
      ReservationLink(project='project', name='res1', zone='us-central1-a'),
      ReservationLink(project='project', name='res2', zone='us-central1-a'),
  ]


def test_get_reservations_list_none(mocker):
  args = mocker.Mock(reservation=None)
  assert get_reservations_list(args) == []


def test_get_reservations_list_empty(mocker):
  args = mocker.Mock(reservation='')
  assert get_reservations_list(args) == []


def test_to_reservation_path():
  res = SubBlockReservationLink(
      project='project',
      name='reservation',
      zone='us-central1-a',
      block_name='block',
      sub_block_name='sub-block',
  )
  assert (
      to_reservation_path(res)
      == 'reservation/reservationBlocks/block/reservationSubBlocks/sub-block'
  )

  res_block = BlockReservationLink(
      project='project',
      name='reservation',
      zone='us-central1-a',
      block_name='block',
  )
  assert to_reservation_path(res_block) == 'reservation/reservationBlocks/block'

  res_simple = ReservationLink(
      project='project', name='reservation', zone='us-central1-a'
  )
  assert to_reservation_path(res_simple) == 'reservation'


def test_assess_available_slices_sub_block(mocker):
  commands_tester = CommandsTester(
      mocker,
      run_command_for_value_path='xpk.core.capacity.run_command_for_value',
  )
  # Mock run_command_for_value to return non-empty string (healthy)
  commands_tester.set_result_for_command(
      (0, '1,0'), 'gcloud beta compute reservations sub-blocks list'
  )
  res = SubBlockReservationLink(
      project='project',
      name='reservation',
      zone='us-central1-a',
      block_name='block',
      sub_block_name='sub-block',
  )
  assert assess_available_slices(
      [res], enable_super_slicing=False, required_hosts=1
  ) == [ReservationCapacity(res, 1)]

  # Mock unhealthy
  commands_tester.set_result_for_command(
      (0, ''), 'gcloud beta compute reservations sub-blocks list'
  )
  assert (
      assess_available_slices(
          [res], enable_super_slicing=False, required_hosts=1
      )
      == []
  )


def test_assess_available_slices_block(mocker):
  commands_tester = CommandsTester(
      mocker,
      run_command_for_value_path='xpk.core.capacity.run_command_for_value',
  )
  # Mock 2 healthy sub-blocks
  commands_tester.set_result_for_command(
      (0, 'sub1,1,0\nsub2,1,0'),
      'gcloud beta compute reservations sub-blocks list',
  )
  res = BlockReservationLink(
      project='project',
      name='reservation',
      zone='us-central1-a',
      block_name='block',
  )
  slices = assess_available_slices(
      [res], enable_super_slicing=False, required_hosts=1
  )
  assert len(slices) == 2
  assert isinstance(slices[0], ReservationCapacity)
  assert isinstance(slices[0].reservation, SubBlockReservationLink)
  assert slices[0].reservation.sub_block_name == 'sub1'
  assert slices[0].reservation.zone == 'us-central1-a'
  assert slices[0].available_count == 1
  assert isinstance(slices[1], ReservationCapacity)
  assert isinstance(slices[1].reservation, SubBlockReservationLink)
  assert slices[1].reservation.sub_block_name == 'sub2'
  assert slices[1].reservation.zone == 'us-central1-a'
  assert slices[1].available_count == 1

  # Mock 0 healthy
  commands_tester.set_result_for_command(
      (0, ''), 'gcloud beta compute reservations sub-blocks list'
  )
  assert (
      assess_available_slices(
          [res], enable_super_slicing=False, required_hosts=1
      )
      == []
  )


def test_assess_available_slices_link_with_blocks(mocker):
  commands_tester = CommandsTester(
      mocker,
      run_command_for_value_path='xpk.core.capacity.run_command_for_value',
  )
  # Mock getting count returning 0 to force block check
  commands_tester.set_result_for_command(
      (0, '0,0,READY'), 'gcloud beta compute reservations describe'
  )
  # Mock getting blocks returning check-able blocks
  commands_tester.set_result_for_command(
      (0, 'block1'), 'gcloud beta compute reservations blocks list'
  )
  commands_tester.set_result_for_command(
      (0, 'sub1,1,0'), 'gcloud beta compute reservations sub-blocks list'
  )

  res = ReservationLink(
      project='project', name='reservation', zone='us-central1-a'
  )
  slices = assess_available_slices(
      [res], enable_super_slicing=True, required_hosts=1
  )
  assert len(slices) == 1
  assert isinstance(slices[0], ReservationCapacity)
  assert isinstance(slices[0].reservation, SubBlockReservationLink)
  assert slices[0].reservation.block_name == 'block1'
  assert slices[0].reservation.sub_block_name == 'sub1'
  assert slices[0].reservation.zone == 'us-central1-a'
  assert slices[0].available_count == 1


def test_assess_available_slices_link_without_blocks(mocker):
  commands_tester = CommandsTester(
      mocker,
      run_command_for_value_path='xpk.core.capacity.run_command_for_value',
  )
  # Mock getting blocks returning empty (fails or no blocks)
  commands_tester.set_result_for_command(
      (1, ''), 'gcloud beta compute reservations blocks list'
  )
  # Mock getting count
  commands_tester.set_result_for_command(
      (0, '2,0,READY'), 'gcloud beta compute reservations describe'
  )

  res = ReservationLink(
      project='project', name='reservation', zone='us-central1-a'
  )
  slices = assess_available_slices(
      [res], enable_super_slicing=False, required_hosts=1
  )
  assert len(slices) == 1
  assert isinstance(slices[0], ReservationCapacity)
  assert isinstance(slices[0].reservation, ReservationLink)
  assert not isinstance(slices[0].reservation, BlockReservationLink)
  assert slices[0].reservation.name == 'reservation'
  assert slices[0].reservation.zone == 'us-central1-a'
  assert slices[0].available_count == 2


def test_assess_available_slices_host_filtering(mocker):
  commands_tester = CommandsTester(
      mocker,
      run_command_for_value_path='xpk.core.capacity.run_command_for_value',
  )
  # Mock a sub-block that has 16 hosts but we need 32
  commands_tester.set_result_for_command(
      (0, 'sub-block,16,0'), 'gcloud beta compute reservations sub-blocks list'
  )
  res = SubBlockReservationLink(
      project='project',
      name='reservation',
      zone='us-central1-a',
      block_name='block',
      sub_block_name='sub-block',
  )
  # Should be empty because available 16 < required 32
  assert (
      assess_available_slices(
          [res], enable_super_slicing=False, required_hosts=32
      )
      == []
  )

  # Mock a reservation that has 48 hosts, and we need 16 per slice.
  # Should return 3 available slices.
  commands_tester.set_result_for_command(
      (0, '48,0,READY'), 'gcloud beta compute reservations describe'
  )
  res_link = ReservationLink(project='p', name='r', zone='z')
  slices = assess_available_slices(
      [res_link], enable_super_slicing=False, required_hosts=16
  )
  assert len(slices) == 1
  assert slices[0].available_count == 3


def test_get_capacity_node_selectors_from_capacity_type():
  # Test with ReservationLink
  res = ReservationLink(
      project='project', name='reservation', zone='us-central1-a'
  )
  node_selector, return_code = get_capacity_node_selectors_from_capacity_type(
      CapacityType.RESERVATION.name, res
  )
  assert return_code == 0
  assert 'cloud.google.com/reservation-name: reservation' in node_selector

  # Test with BlockReservationLink
  res_block = BlockReservationLink(
      project='project',
      name='reservation',
      zone='us-central1-a',
      block_name='block',
  )
  node_selector, return_code = get_capacity_node_selectors_from_capacity_type(
      CapacityType.RESERVATION.name, res_block
  )
  assert return_code == 0
  assert (
      'cloud.google.com/reservation-name: reservation/reservationBlocks/block'
      in node_selector
  )

  # Test with other capacity types
  node_selector, return_code = get_capacity_node_selectors_from_capacity_type(
      CapacityType.ON_DEMAND.name, None
  )
  assert return_code == 0
  assert node_selector == ''

  node_selector, return_code = get_capacity_node_selectors_from_capacity_type(
      CapacityType.SPOT.name, None
  )
  assert return_code == 0
  assert 'cloud.google.com/gke-spot: "true"' in node_selector

  node_selector, return_code = get_capacity_node_selectors_from_capacity_type(
      CapacityType.FLEX_START.name, None
  )
  assert return_code == 0
  assert 'cloud.google.com/gke-queued: "true"' in node_selector

  # Test with unknown capacity type
  node_selector, return_code = get_capacity_node_selectors_from_capacity_type(
      'UNKNOWN_TYPE', None
  )
  assert return_code == 1
