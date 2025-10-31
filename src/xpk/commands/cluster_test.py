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

from argparse import Namespace
from dataclasses import dataclass
from unittest.mock import MagicMock, patch
import pytest

from xpk.commands.cluster import _install_kueue, _validate_cluster_create_args
from xpk.core.system_characteristics import SystemCharacteristics, UserFacingNameToSystemCharacteristics
from xpk.utils.feature_flags import FeatureFlags


@dataclass
class _Mocks:
  common_print_mock: MagicMock
  commands_print_mock: MagicMock
  commands_get_reservation_deployment_type: MagicMock


@pytest.fixture
def mock_common_print_and_exit(mocker):
  common_print_mock = mocker.patch(
      'xpk.commands.common.xpk_print',
      return_value=None,
  )
  commands_print_mock = mocker.patch(
      'xpk.commands.cluster.xpk_print', return_value=None
  )
  commands_get_reservation_deployment_type = mocker.patch(
      'xpk.commands.cluster.get_reservation_deployment_type',
      return_value='DENSE',
  )
  return _Mocks(
      common_print_mock=common_print_mock,
      commands_get_reservation_deployment_type=commands_get_reservation_deployment_type,
      commands_print_mock=commands_print_mock,
  )


DEFAULT_TEST_SYSTEM: SystemCharacteristics = (
    UserFacingNameToSystemCharacteristics['l4-1']
)
SUB_SLICING_SYSTEM: SystemCharacteristics = (
    UserFacingNameToSystemCharacteristics['v6e-4x4']
)


def test_validate_cluster_create_args_for_correct_args_pass(
    mock_common_print_and_exit: _Mocks,
):
  args = Namespace()

  _validate_cluster_create_args(args, DEFAULT_TEST_SYSTEM)

  assert mock_common_print_and_exit.common_print_mock.call_count == 0


def test_validate_cluster_create_args_for_correct_sub_slicing_args_pass(
    mock_common_print_and_exit: _Mocks,
):
  FeatureFlags.SUB_SLICING_ENABLED = True
  args = Namespace(
      sub_slicing=True,
      reservation='test-reservation',
      project='project',
      zone='zone',
  )

  _validate_cluster_create_args(args, SUB_SLICING_SYSTEM)

  assert mock_common_print_and_exit.common_print_mock.call_count == 0


def test_validate_cluster_create_args_for_not_supported_system_throws(
    mock_common_print_and_exit: _Mocks,
):
  FeatureFlags.SUB_SLICING_ENABLED = True
  args = Namespace(
      sub_slicing=True,
      reservation='test-reservation',
      project='project',
      zone='zone',
  )

  with pytest.raises(SystemExit):
    _validate_cluster_create_args(args, DEFAULT_TEST_SYSTEM)

  assert mock_common_print_and_exit.common_print_mock.call_count == 1
  assert (
      mock_common_print_and_exit.common_print_mock.call_args[0][0]
      == 'Error: l4-1 does not support Sub-slicing.'
  )


def test_validate_cluster_create_args_for_missing_reservation(
    mock_common_print_and_exit: _Mocks,
):
  FeatureFlags.SUB_SLICING_ENABLED = True
  args = Namespace(
      sub_slicing=True, project='project', zone='zone', reservation=None
  )

  with pytest.raises(SystemExit):
    _validate_cluster_create_args(args, SUB_SLICING_SYSTEM)

  assert mock_common_print_and_exit.commands_print_mock.call_count == 1
  assert (
      'Validation failed: Sub-slicing cluster creation requires'
      in mock_common_print_and_exit.commands_print_mock.call_args[0][0]
  )


def test_validate_cluster_create_args_for_invalid_reservation(
    mock_common_print_and_exit: _Mocks,
):
  FeatureFlags.SUB_SLICING_ENABLED = True
  args = Namespace(
      sub_slicing=True,
      project='project',
      zone='zone',
      reservation='test-reservation',
  )
  mock_common_print_and_exit.commands_get_reservation_deployment_type.return_value = (
      'SPARSE'
  )

  with pytest.raises(SystemExit):
    _validate_cluster_create_args(args, SUB_SLICING_SYSTEM)

  assert mock_common_print_and_exit.commands_print_mock.call_count == 5
  assert (
      'Refer to the documentation for more information on creating Cluster'
      in mock_common_print_and_exit.commands_print_mock.call_args[0][0]
  )


@patch('xpk.commands.cluster.KueueManager.install_or_upgrade')
def test_install_kueue_returns_kueue_installation_code(
    mock_kueue_manager_install: MagicMock,
):
  mock_kueue_manager_install.return_value = 17

  code = _install_kueue(
      args=Namespace(
          num_slices=1,
          num_nodes=1,
          flex=False,
          memory_limit='100Gi',
          cpu_limit=100,
          enable_pathways=False,
          sub_slicing=False,
      ),
      system=DEFAULT_TEST_SYSTEM,
      autoprovisioning_config=None,
  )

  assert code == 17
