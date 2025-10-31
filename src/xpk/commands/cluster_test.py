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
from typing import Any
from unittest.mock import MagicMock, patch
import pytest

from xpk.commands.cluster import _install_kueue, _validate_cluster_create_args, run_gke_cluster_create_command
from xpk.core.system_characteristics import SystemCharacteristics, UserFacingNameToSystemCharacteristics
from xpk.core.testing.commands_tester import CommandsTester
from xpk.utils.feature_flags import FeatureFlags


@dataclass
class _Mocks:
  common_print_mock: MagicMock
  commands_print_mock: MagicMock
  commands_get_reservation_deployment_type: MagicMock
  commands_tester: CommandsTester


@pytest.fixture
def mocks(mocker) -> _Mocks:
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
      commands_tester=CommandsTester(
          mocker,
          run_command_with_updates_path=(
              'xpk.commands.cluster.run_command_with_updates'
          ),
      ),
  )


def construct_args(**kwargs: Any) -> Namespace:
  args_dict = dict(
      project='project',
      zone='us-central1-a',
      reservation='',
      default_pool_cpu_machine_type='test-machine-type',
      cluster='test-cluster',
      default_pool_cpu_num_nodes='100',
      sub_slicing=False,
      gke_version='',
      private=False,
      authorized_networks=None,
      enable_pathways=False,
      enable_ray_cluster=False,
      enable_workload_identity=False,
      enable_gcsfuse_csi_driver=False,
      enable_gcpfilestore_csi_driver=False,
      enable_parallelstore_csi_driver=False,
      enable_pd_csi_driver=False,
      enable_lustre_csi_driver=False,
      custom_cluster_arguments='',
      num_slices=1,
      num_nodes=1,
      flex=False,
      memory_limit='100Gi',
      cpu_limit=100,
      cluster_cpu_machine_type='',
  )
  args_dict.update(kwargs)
  return Namespace(**args_dict)


GPU_TEST_SYSTEM: SystemCharacteristics = UserFacingNameToSystemCharacteristics[
    'l4-1'
]
SUB_SLICING_SYSTEM: SystemCharacteristics = (
    UserFacingNameToSystemCharacteristics['v6e-4x4']
)
TPU_TEST_SYSTEM: SystemCharacteristics = UserFacingNameToSystemCharacteristics[
    'v6e-4x4'
]


def test_validate_cluster_create_args_for_correct_args_pass(
    mocks: _Mocks,
):
  args = Namespace()

  _validate_cluster_create_args(args, GPU_TEST_SYSTEM)

  assert mocks.common_print_mock.call_count == 0


def test_validate_cluster_create_args_for_correct_sub_slicing_args_pass(
    mocks: _Mocks,
):
  FeatureFlags.SUB_SLICING_ENABLED = True
  args = construct_args(
      sub_slicing=True,
      reservation='test-reservation',
  )

  _validate_cluster_create_args(args, SUB_SLICING_SYSTEM)

  assert mocks.common_print_mock.call_count == 0


def test_validate_cluster_create_args_for_not_supported_system_throws(
    mocks: _Mocks,
):
  FeatureFlags.SUB_SLICING_ENABLED = True
  args = construct_args(
      sub_slicing=True,
      reservation='test-reservation',
  )

  with pytest.raises(SystemExit):
    _validate_cluster_create_args(args, GPU_TEST_SYSTEM)

  assert mocks.common_print_mock.call_count == 1
  assert (
      mocks.common_print_mock.call_args[0][0]
      == 'Error: l4-1 does not support Sub-slicing.'
  )


def test_validate_cluster_create_args_for_missing_reservation(
    mocks: _Mocks,
):
  FeatureFlags.SUB_SLICING_ENABLED = True
  args = construct_args(
      sub_slicing=True,
      reservation=None,
  )

  with pytest.raises(SystemExit):
    _validate_cluster_create_args(args, SUB_SLICING_SYSTEM)

  assert mocks.commands_print_mock.call_count == 1
  assert (
      'Validation failed: Sub-slicing cluster creation requires'
      in mocks.commands_print_mock.call_args[0][0]
  )


def test_validate_cluster_create_args_for_invalid_reservation(
    mocks: _Mocks,
):
  FeatureFlags.SUB_SLICING_ENABLED = True
  args = construct_args(
      sub_slicing=True,
      reservation='test-reservation',
  )
  mocks.commands_get_reservation_deployment_type.return_value = 'SPARSE'

  with pytest.raises(SystemExit):
    _validate_cluster_create_args(args, SUB_SLICING_SYSTEM)

  assert mocks.commands_print_mock.call_count == 5
  assert (
      'Refer to the documentation for more information on creating Cluster'
      in mocks.commands_print_mock.call_args[0][0]
  )


@patch('xpk.commands.cluster.KueueManager.install_or_upgrade')
def test_install_kueue_returns_kueue_installation_code(
    mock_kueue_manager_install: MagicMock,
):
  mock_kueue_manager_install.return_value = 17

  code = _install_kueue(
      args=construct_args(),
      system=GPU_TEST_SYSTEM,
      autoprovisioning_config=None,
  )

  assert code == 17


def test_run_gke_cluster_create_command_specifies_custom_cluster_arguments_last(
    mocks: _Mocks,
):
  result = run_gke_cluster_create_command(
      args=construct_args(
          custom_cluster_arguments='--enable-autoscaling=False --foo=baz'
      ),
      gke_control_plane_version='1.2.3',
      system=TPU_TEST_SYSTEM,
  )

  assert result == 0
  mocks.commands_tester.assert_command_run(
      'clusters create',
      ' --enable-autoscaling',
      ' --enable-autoscaling=False --foo=baz',
  )


def test_run_gke_cluster_create_command_without_gke_version_does_not_have_no_autoupgrade_flag(
    mocks: _Mocks,
):
  result = run_gke_cluster_create_command(
      args=construct_args(gke_version=''),
      gke_control_plane_version='1.2.3',
      system=TPU_TEST_SYSTEM,
  )

  assert result == 0
  mocks.commands_tester.assert_command_not_run(
      'clusters create', ' --no-enable-autoupgrade'
  )


def test_run_gke_cluster_create_command_with_gke_version_has_no_autoupgrade_flag(
    mocks: _Mocks,
):
  result = run_gke_cluster_create_command(
      args=construct_args(gke_version='1.2.3'),
      gke_control_plane_version='1.2.3',
      system=TPU_TEST_SYSTEM,
  )

  assert result == 0
  mocks.commands_tester.assert_command_run(
      'clusters create', ' --no-enable-autoupgrade'
  )


def test_run_gke_cluster_create_command_with_gpu_system_has_no_enable_autoupgrade(
    mocks: _Mocks,
):
  result = run_gke_cluster_create_command(
      args=construct_args(gke_version=''),
      gke_control_plane_version='1.2.3',
      system=GPU_TEST_SYSTEM,
  )

  assert result == 0
  mocks.commands_tester.assert_command_run(
      'clusters create', ' --no-enable-autoupgrade'
  )
