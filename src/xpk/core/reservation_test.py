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

from .testing.commands_tester import CommandsTester
from .reservation import (
    get_reservation_deployment_type,
    get_reservation_placement_policy,
    get_reservation_maintenance_interval,
    parse_reservation,
    verify_reservations_exist,
    get_reservations_list,
    ReservationLink,
    BlockReservationLink,
    SubBlockReservationLink,
    to_reservation_path,
    _parse_reservation,
    SpecificReservation,
    AggregateReservation,
    AcceleratorResource,
    Reservation,
    get_reservation_cached,
)


@pytest.fixture(autouse=True)
def commands_tester(mocker):
  return CommandsTester(mocker)


@pytest.fixture(autouse=True)
def clear_capacity_cache():
  get_reservation_cached.cache_clear()
  yield
  get_reservation_cached.cache_clear()


@patch('xpk.core.reservation.get_reservation_cached')
@patch('xpk.core.reservation.xpk_print')
def test_get_reservation_deployment_type_exits_on_failure(
    mock_print, mock_get_cached
):
  mock_get_cached.return_value = None
  res_link = ReservationLink(project='project', name='reservation', zone='zone')

  with pytest.raises(SystemExit):
    get_reservation_deployment_type(res_link)
  mock_print.assert_called()


@patch('xpk.core.reservation.get_reservation_cached')
def test_get_reservation_deployment_type(mock_get_cached):
  mock_res = MagicMock(spec=Reservation)
  mock_res.deployment_type = 'DENSE'
  mock_get_cached.return_value = mock_res

  res_link = ReservationLink(project='project', name='reservation', zone='zone')

  result = get_reservation_deployment_type(res_link)

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
@patch('xpk.core.reservation.xpk_print')
def test_parse_reservation_fails_on_invalid_reservations(
    xpk_print: MagicMock, reservation_path: str
):
  with pytest.raises(SystemExit):
    parse_reservation(reservation_path, 'cluster-project', 'zone')

  assert 'Unable to parse reservation' in xpk_print.mock_calls[0].args[0]


@patch('xpk.core.reservation.get_reservation_cached')
def test_verify_reservations_exist_success(mock_get_cached, mocker):
  mock_get_cached.return_value = MagicMock(spec=Reservation)
  args = mocker.Mock(reservation='r1,r2', project='project', zone='zone')

  result = verify_reservations_exist(args)

  assert result == 0
  assert mock_get_cached.call_count == 2
  mock_get_cached.assert_any_call(
      ReservationLink(project='project', zone='zone', name='r1')
  )
  mock_get_cached.assert_any_call(
      ReservationLink(project='project', zone='zone', name='r2')
  )


@patch('xpk.core.reservation.get_reservation_cached')
def test_verify_reservations_exist_failure(mock_get_cached, mocker):
  mock_get_cached.side_effect = [
      MagicMock(),
      None,
  ]  # First exists, second fails
  args = mocker.Mock(reservation='r1,r2', project='project', zone='zone')

  result = verify_reservations_exist(args)

  assert result == 1
  assert mock_get_cached.call_count == 2


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


@patch('xpk.core.reservation.get_reservation_cached')
def test_get_reservation_placement_policy(mock_get_cached):
  mock_res = MagicMock(spec=Reservation)
  mock_res.resource_policy = 'compact'
  mock_get_cached.return_value = mock_res

  res_link = ReservationLink(project='project', name='reservation', zone='zone')

  result = get_reservation_placement_policy(res_link)

  assert result == 'compact'


@patch('xpk.core.reservation.get_reservation_cached')
def test_get_reservation_maintenance_interval(mock_get_cached):
  mock_res = MagicMock(spec=Reservation)
  mock_res.specific_reservation = MagicMock(spec=SpecificReservation)
  mock_res.specific_reservation.maintenance_interval = 'PERIODIC'
  mock_get_cached.return_value = mock_res

  res_link = ReservationLink(project='project', name='reservation', zone='zone')

  result = get_reservation_maintenance_interval(res_link)

  assert result == 'PERIODIC'


def test_parse_reservation_without_specific_or_aggregate():
  data = {
      'deploymentType': 'DENSE',
      'resourcePolicies': {'policy': 'compact-policy'},
      'status': 'READY',
  }

  reservation = _parse_reservation('res1', data)

  assert reservation == Reservation(
      name='res1',
      aggregate_reservation=None,
      specific_reservation=None,
      deployment_type='DENSE',
      resource_policy='compact-policy',
  )


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

  reservation = _parse_reservation('res1', data)

  assert reservation == Reservation(
      name='res1',
      aggregate_reservation=None,
      specific_reservation=SpecificReservation(
          count=10,
          in_use_count=2,
          machine_type='test-machine',
          guest_accelerators=[
              AcceleratorResource(
                  accelerator_count=1, accelerator_type='nvidia-test'
              )
          ],
      ),
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

  reservation = _parse_reservation('res1', data)

  assert reservation == Reservation(
      name='res1',
      specific_reservation=None,
      aggregate_reservation=AggregateReservation(
          reserved_resources=[
              AcceleratorResource(accelerator_count=100, accelerator_type='tpu')
          ],
          in_use_resources=[
              AcceleratorResource(accelerator_count=20, accelerator_type='tpu')
          ],
      ),
  )


def test_get_reservation_cached_caching(commands_tester: CommandsTester):
  commands_tester.set_result_for_command(
      (0, '{"name": "res", "status": "READY"}'), 'reservations', 'describe'
  )

  # First call
  get_reservation_cached(ReservationLink('project', 'res1', 'zone'))
  commands_tester.assert_command_run(
      'reservations', 'describe', 'res1', times=1
  )

  # Second call with same args
  get_reservation_cached(ReservationLink('project', 'res1', 'zone'))
  commands_tester.assert_command_run(
      'reservations', 'describe', 'res1', times=1
  )

  # Third call with different args
  get_reservation_cached(ReservationLink('project', 'res2', 'zone'))
  commands_tester.assert_command_run(
      'reservations', 'describe', 'res2', times=1
  )


def test_get_reservation_cached_calls_correct_command(
    commands_tester: CommandsTester,
):
  commands_tester.set_result_for_command(
      (0, '{"name": "res", "status": "READY"}'),
      'reservations describe my-res',
  )
  reservation = ReservationLink(
      project='my-project', name='my-res', zone='my-zone'
  )

  get_reservation_cached(reservation)

  commands_tester.assert_command_run(
      'gcloud beta compute reservations describe my-res',
      '--project=my-project --zone=my-zone',
  )


def test_get_reservation_cached_returns_none_if_not_ready(
    commands_tester: CommandsTester,
):
  commands_tester.set_result_for_command(
      (0, '{"name": "res", "status": "CREATING"}'),
      'reservations describe res',
  )
  reservation = ReservationLink(project='project', name='res', zone='zone')

  result = get_reservation_cached(reservation)

  assert result is None


def test_get_reservation_cached_returns_none_on_command_failure(
    commands_tester: CommandsTester,
):
  commands_tester.set_result_for_command(
      (1, 'Error message'), 'reservations', 'describe', 'res'
  )
  reservation = ReservationLink(project='project', name='res', zone='zone')

  result = get_reservation_cached(reservation)

  assert result is None


def test_get_reservation_cached_returns_none_on_invalid_json(
    commands_tester, mocker
):
  commands_tester.set_result_for_command(
      (0, 'invalid json'), 'reservations', 'describe', 'res'
  )
  mock_print = mocker.patch('xpk.core.reservation.xpk_print')
  reservation = ReservationLink(project='project', name='res', zone='zone')

  result = get_reservation_cached(reservation)

  assert result is None
  mock_print.assert_called()
