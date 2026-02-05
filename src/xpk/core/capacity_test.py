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
    ReservationLink,
    BlockReservationLink,
    SubBlockReservationLink,
    get_capacity_type,
    CapacityType,
    verify_reservations_exist,
    get_reservations_list,
    to_reservation_path,
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
        reservation=ReservationLink(project='p', name='r', zone='z')
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
      reservation=ReservationLink(project='p', name='r', zone='z')
  )
  assert result == 'DENSE'


@pytest.mark.parametrize(
    argnames='reservation_path,expected_reservation',
    argvalues=[
        (
            'reservation',
            ReservationLink(project='cluster-project', name='reservation', zone='zone'),
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
  actual_reservation = parse_reservation(reservation_path, 'cluster-project', 'zone')

  assert actual_reservation == expected_reservation


def test_to_reservation_path():
  res = ReservationLink(project='p', name='r', zone='z')
  assert to_reservation_path(res) == 'r'

  res_block = BlockReservationLink(project='p', name='r', zone='z', block_name='b')
  assert to_reservation_path(res_block) == 'r/reservationBlocks/b'

  res_sub = SubBlockReservationLink(
      project='p', name='r', zone='z', block_name='b', sub_block_name='s'
  )
  assert to_reservation_path(res_sub) == 'r/reservationBlocks/b/reservationSubBlocks/s'


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
