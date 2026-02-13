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
    get_reservation_placement_policy,
    get_reservation_maintenance_interval,
    parse_reservation,
    get_capacity_type,
    CapacityType,
    verify_reservations_exist,
    get_reservations_list,
    ReservationLink,
    BlockReservationLink,
    SubBlockReservationLink,
    _parse_reservation,
    _SpecificReservation,
    _AcceleratorResource,
    _Reservation,
    _get_reservation_cached,
)
from xpk.core.testing.commands_tester import CommandsTester
from .system_characteristics import SystemCharacteristics, AcceleratorType, DockerPlatform


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


@patch('xpk.core.capacity._get_reservation_cached')
def test_get_reservation_deployment_type_uses_cached(mock_get_cached):
  mock_res = MagicMock(spec=_Reservation)
  mock_res.deployment_type = 'DENSE'
  mock_get_cached.return_value = mock_res

  res_link = ReservationLink(project='p', name='r', zone='z')

  result = get_reservation_deployment_type(res_link)

  assert result == 'DENSE'
  mock_get_cached.assert_called_once_with(
      ReservationLink(project='p', zone='z', name='r')
  )


@patch('xpk.core.capacity._get_reservation_cached')
def test_get_reservation_placement_policy_uses_cached(mock_get_cached):
  mock_res = MagicMock(spec=_Reservation)
  mock_res.resource_policy = 'compact'
  mock_get_cached.return_value = mock_res

  res_link = ReservationLink(project='p', name='r', zone='z')

  result = get_reservation_placement_policy(res_link)

  assert result == 'compact'
  mock_get_cached.assert_called_once_with(
      ReservationLink(project='p', zone='z', name='r')
  )


@patch('xpk.core.capacity._get_reservation_cached')
def test_get_reservation_maintenance_interval_uses_cached(mock_get_cached):
  mock_res = MagicMock(spec=_Reservation)
  mock_res.specificReservation = MagicMock(spec=_SpecificReservation)
  mock_res.specificReservation.maintenance_interval = 'PERIODIC'
  mock_get_cached.return_value = mock_res

  res_link = ReservationLink(project='p', name='r', zone='z')

  result = get_reservation_maintenance_interval(res_link)

  assert result == 'PERIODIC'
  mock_get_cached.assert_called_once_with(
      ReservationLink(project='p', zone='z', name='r')
  )


@patch('xpk.core.capacity._get_reservation_cached')
def test_verify_reservations_exist_uses_cached_success(mock_get_cached, mocker):
  mock_get_cached.return_value = MagicMock(spec=_Reservation)

  args = mocker.Mock(reservation='r1,r2', project='p', zone='z')

  assert verify_reservations_exist(args) == 0
  assert mock_get_cached.call_count == 2
  mock_get_cached.assert_any_call(
      ReservationLink(project='p', zone='z', name='r1')
  )
  mock_get_cached.assert_any_call(
      ReservationLink(project='p', zone='z', name='r2')
  )


@patch('xpk.core.capacity._get_reservation_cached')
def test_verify_reservations_exist_uses_cached_failure(mock_get_cached, mocker):
  mock_get_cached.side_effect = [
      MagicMock(),
      None,
  ]  # First exists, second fails

  args = mocker.Mock(reservation='r1,r2', project='p', zone='z')

  assert verify_reservations_exist(args) == 1
  assert mock_get_cached.call_count == 2


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


def test_get_reservation_cached_caching(mocker):
  mock_run_command = mocker.patch(
      'xpk.core.capacity.run_command_for_value',
      return_value=(0, '{"name": "res", "status": "READY"}'),
  )

  # First call
  _get_reservation_cached(ReservationLink('project', 'res1', 'zone'))
  assert mock_run_command.call_count == 1

  # Second call with same args
  _get_reservation_cached(ReservationLink('project', 'res1', 'zone'))
  assert mock_run_command.call_count == 1  # Should still be 1

  # Third call with different args
  _get_reservation_cached(ReservationLink('project', 'res2', 'zone'))
  assert mock_run_command.call_count == 2


def test_parse_reservation_with_new_fields():
  data = {
      'specificReservation': {
          'count': '10',
          'inUseCount': '2',
          'instanceProperties': {
              'machineType': 'test-machine',
              'maintenanceInterval': 'PERIODIC',
          },
      },
      'deploymentType': 'DENSE',
      'resourcePolicies': {'policy': 'compact-policy'},
      'status': 'READY',
  }

  res = _parse_reservation('res1', data)

  assert res.name == 'res1'
  assert res.deployment_type == 'DENSE'
  assert res.resource_policy == 'compact-policy'
  assert res.specificReservation.maintenance_interval == 'PERIODIC'


def test_parse_reservation_defaults_new_fields():
  data = {
      'specificReservation': {
          'count': '10',
          'inUseCount': '2',
          'instanceProperties': {
              'machineType': 'test-machine',
          },
      },
      'status': 'READY',
  }

  res = _parse_reservation('res1', data)

  assert res.name == 'res1'
  assert res.deployment_type == ''
  assert res.resource_policy == ''
  assert res.specificReservation.maintenance_interval == ''
