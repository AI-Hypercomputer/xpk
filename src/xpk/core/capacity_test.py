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
from .capacity import get_reservation_deployment_type, get_reservation_project_and_name


@patch('xpk.core.capacity.xpk_print')
def test_get_reservation_deployment_type_exits_with_command_fails(
    xpk_print: MagicMock, mocker
):
  mocker.patch(
      target='xpk.core.capacity.run_command_for_value', return_value=(1, '')
  )
  with pytest.raises(SystemExit):
    get_reservation_deployment_type(
        reservation='reservation', zone='zone', project='project'
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
      reservation='reservation', zone='zone', project='project'
  )
  assert result == 'DENSE'


def test_get_reservation_project_and_name_parses_local_reservation():
  project, name = get_reservation_project_and_name(
      'test-reservation', 'cluster-project'
  )

  assert project == 'cluster-project'
  assert name == 'test-reservation'


def test_get_reservation_project_and_name_parses_shared_reservation():
  project, name = get_reservation_project_and_name(
      'projects/reservation-project/reservations/test-reservation',
      'cluster-project',
  )

  assert project == 'reservation-project'
  assert name == 'test-reservation'


@patch('xpk.core.capacity.xpk_print')
def test_get_reservation_project_and_name_fails_for_invalid_reservation(
    xpk_print: MagicMock, mocker
):
  with pytest.raises(SystemExit):
    get_reservation_project_and_name(
        'invalid/reservation',
        'cluster-project',
    )
  assert 'Unable to parse reservation' in xpk_print.mock_calls[0].args[0]
