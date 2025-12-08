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
from .capacity import get_reservation_deployment_type, parse_reservation, Reservation


@patch('xpk.core.capacity.xpk_print')
def test_get_reservation_deployment_type_exits_with_command_fails(
    xpk_print: MagicMock, mocker
):
  mocker.patch(
      target='xpk.core.capacity.run_command_for_value', return_value=(1, '')
  )
  with pytest.raises(SystemExit):
    get_reservation_deployment_type(
        reservation_path='reservation', zone='zone', project='project'
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
      reservation_path='reservation', zone='zone', project='project'
  )
  assert result == 'DENSE'


@pytest.mark.parametrize(
    argnames='reservation_path,expected_reservation',
    argvalues=[
        (
            'reservation',
            Reservation(project='cluster-project', name='reservation'),
        ),
        (
            'reservation/reservationBlocks/block',
            Reservation(
                project='cluster-project',
                name='reservation',
                block_name='block',
            ),
        ),
        (
            'reservation/reservationBlocks/block/reservationSubBlocks/subblock',
            Reservation(
                project='cluster-project',
                name='reservation',
                block_name='block',
                sub_block_name='subblock',
            ),
        ),
        (
            'projects/p/reservations/reservation',
            Reservation(project='p', name='reservation'),
        ),
        (
            'projects/p/reservations/reservation/reservationBlocks/block',
            Reservation(
                project='p',
                name='reservation',
                block_name='block',
            ),
        ),
        (
            'projects/p/reservations/reservation/reservationBlocks/block/reservationSubBlocks/subblock',
            Reservation(
                project='p',
                name='reservation',
                block_name='block',
                sub_block_name='subblock',
            ),
        ),
    ],
)
def test_parse_reservation_parses_valid_reservations(
    reservation_path: str,
    expected_reservation: Reservation,
):
  actual_reservation = parse_reservation(reservation_path, 'cluster-project')

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
    parse_reservation(reservation_path, 'cluster-project')

  assert 'Unable to parse reservation' in xpk_print.mock_calls[0].args[0]
