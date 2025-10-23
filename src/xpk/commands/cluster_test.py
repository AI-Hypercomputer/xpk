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
from unittest.mock import MagicMock
import pytest

from xpk.commands.cluster import _validate_cluster_create_args
from xpk.core.system_characteristics import SystemCharacteristics, UserFacingNameToSystemCharacteristics
from xpk.utils.feature_flags import FeatureFlags


@dataclass
class _Mocks:
  common_print_mock: MagicMock
  common_exit_mock: MagicMock


@pytest.fixture
def mock_common_print_and_exit(mocker):
  common_print_mock = mocker.patch(
      'xpk.commands.common.xpk_print',
      return_value=None,
  )
  common_exit_mock = mocker.patch(
      'xpk.commands.common.xpk_exit',
      return_value=None,
  )
  return _Mocks(
      common_print_mock=common_print_mock, common_exit_mock=common_exit_mock
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
  assert mock_common_print_and_exit.common_exit_mock.call_count == 0


def test_validate_cluster_create_args_for_correct_sub_slicing_args_pass(
    mock_common_print_and_exit: _Mocks,
):
  FeatureFlags.SUB_SLICING_ENABLED = True
  args = Namespace(sub_slicing=True)

  _validate_cluster_create_args(args, SUB_SLICING_SYSTEM)

  assert mock_common_print_and_exit.common_print_mock.call_count == 0
  assert mock_common_print_and_exit.common_exit_mock.call_count == 0


def test_validate_cluster_create_args_for_not_supported_system_throws(
    mock_common_print_and_exit: _Mocks,
):
  FeatureFlags.SUB_SLICING_ENABLED = True
  args = Namespace(sub_slicing=True)

  _validate_cluster_create_args(args, DEFAULT_TEST_SYSTEM)

  assert mock_common_print_and_exit.common_print_mock.call_count == 1
  assert (
      mock_common_print_and_exit.common_print_mock.call_args[0][0]
      == 'Error: l4-1 does not support Sub-slicing.'
  )
  assert mock_common_print_and_exit.common_exit_mock.call_count == 1
