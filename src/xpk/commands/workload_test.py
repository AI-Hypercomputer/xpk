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

import dataclasses
from unittest.mock import MagicMock, patch
import yaml
import pytest
from ..core.system_characteristics import DockerPlatform, SystemCharacteristics, AcceleratorType, UserFacingNameToSystemCharacteristics, GpuConfig
from .workload import _validate_sub_slicing_topology, _validate_sub_slicing_availability, workload_create
from packaging.version import Version
from .cluster_test import construct_args


SYSTEM_CHARACTERISTICS = SystemCharacteristics(
    topology='8x8',
    vms_per_slice=1,
    gke_accelerator='nvidia-l4',
    gce_machine_type='g2-standard-12',
    chips_per_vm=1,
    accelerator_type=AcceleratorType.TPU,
    device_type='l4-1',
    supports_sub_slicing=True,
    requires_workload_policy=False,
    docker_platform=DockerPlatform.AMD,
)


@dataclasses.dataclass
class _WorkloadCreateMocks:
  """Holds all the mocked dependencies for the workload_create function."""

  get_user_workload_container: MagicMock
  get_gpu_scheduler: MagicMock
  get_storages_to_mount: MagicMock
  add_bucket_iam_members: MagicMock
  get_gke_outlier_dashboard: MagicMock
  check_if_workload_exists: MagicMock
  get_cluster_configmap: MagicMock
  check_if_workload_can_schedule: MagicMock
  setup_k8s_env: MagicMock
  setup_k8s_service_accounts: MagicMock
  validate_dependencies_list: MagicMock
  write_tmp_file: MagicMock
  validate_sub_slicing_availability: MagicMock
  get_cluster_capacity_type: MagicMock
  is_TAS_possible: MagicMock
  validate_sub_slicing_topology: MagicMock
  get_cluster_location: MagicMock
  xpk_exit: MagicMock
  run_command_with_updates: MagicMock


@pytest.fixture
def xpk_print(mocker):
  return mocker.patch('xpk.commands.workload.xpk_print')


@pytest.fixture
def workload_create_mocks(mocker) -> _WorkloadCreateMocks:
  """Mocks all dependencies for the workload_create function."""
  return _WorkloadCreateMocks(
      get_user_workload_container=mocker.patch(
          'xpk.commands.workload.get_user_workload_container',
          return_value=('', None),
      ),
      get_gpu_scheduler=mocker.patch(
          'xpk.commands.workload.get_gpu_scheduler', return_value=('', 0)
      ),
      get_storages_to_mount=mocker.patch(
          'xpk.commands.workload.get_storages_to_mount', return_value=[]
      ),
      add_bucket_iam_members=mocker.patch(
          'xpk.commands.workload.add_bucket_iam_members'
      ),
      get_gke_outlier_dashboard=mocker.patch(
          'xpk.commands.workload.get_gke_outlier_dashboard'
      ),
      check_if_workload_exists=mocker.patch(
          'xpk.commands.workload.check_if_workload_exists', return_value=False
      ),
      get_cluster_configmap=mocker.patch(
          'xpk.commands.workload.get_cluster_configmap', return_value={}
      ),
      check_if_workload_can_schedule=mocker.patch(
          'xpk.commands.workload.check_if_workload_can_schedule',
          return_value=True,
      ),
      setup_k8s_env=mocker.patch('xpk.commands.workload.setup_k8s_env'),
      setup_k8s_service_accounts=mocker.patch(
          'xpk.commands.workload.setup_k8s_service_accounts'
      ),
      validate_dependencies_list=mocker.patch(
          'xpk.commands.workload.validate_dependencies_list'
      ),
      write_tmp_file=mocker.patch('xpk.commands.workload.write_tmp_file'),
      validate_sub_slicing_availability=mocker.patch(
          'xpk.commands.workload._validate_sub_slicing_availability'
      ),
      get_cluster_capacity_type=mocker.patch(
          'xpk.commands.workload.get_cluster_capacity_type',
          return_value='on-demand',
      ),
      is_TAS_possible=mocker.patch(
          'xpk.commands.workload.is_TAS_possible', return_value=False
      ),
      validate_sub_slicing_topology=mocker.patch(
          'xpk.commands.workload._validate_sub_slicing_topology'
      ),
      get_cluster_location=mocker.patch(
          'xpk.commands.workload.get_cluster_location',
          return_value='us-central1',
      ),
      xpk_exit=mocker.patch('xpk.commands.workload.xpk_exit'),
      run_command_with_updates=mocker.patch(
          'xpk.commands.workload.run_command_with_updates', return_value=0
      ),
  )


def test_validate_sub_slicing_topology_exits_for_unsupported_topology(
    xpk_print: MagicMock,
):
  with pytest.raises(SystemExit):
    _validate_sub_slicing_topology(SYSTEM_CHARACTERISTICS, '2x1')

  assert (
      'shape is invalid. It has to be one of' in xpk_print.mock_calls[0].args[0]
  )


def test_validate_sub_slicing_topology_exits_for_too_large_topology(
    xpk_print: MagicMock,
):
  with pytest.raises(SystemExit):
    _validate_sub_slicing_topology(SYSTEM_CHARACTERISTICS, '16x16')

  assert (
      'shape is too large. The shape cannot be'
      in xpk_print.mock_calls[0].args[0]
  )


def test_validate_sub_slicing_topology_does_nothing_for_supported_topology():
  _validate_sub_slicing_topology(SYSTEM_CHARACTERISTICS, '4x4')


def test_validate_sub_slicing_availability_exits_when_getting_topologies_fails(
    xpk_print: MagicMock, mocker
):
  mocker.patch(
      'xpk.commands.workload.has_sub_slicing_enabled',
      return_value=(1, None),
  )
  with pytest.raises(SystemExit):
    _validate_sub_slicing_availability()

  assert (
      'Unable to validate sub-slicing support'
      in xpk_print.mock_calls[0].args[0]
  )


def test_validate_sub_slicing_availability_exits_when_subslicing_topology_is_not_defined(
    xpk_print: MagicMock, mocker
):
  mocker.patch(
      'xpk.commands.workload.has_sub_slicing_enabled',
      return_value=(0, False),
  )
  with pytest.raises(SystemExit):
    _validate_sub_slicing_availability()

  assert (
      'Cluster has not been not set up for Sub-slicing.'
      in xpk_print.mock_calls[0].args[0]
  )


def test_validate_sub_slicing_availability_exits_when_kueue_version_cannot_be_determined(
    xpk_print: MagicMock, mocker
):
  mocker.patch(
      'xpk.commands.workload.has_sub_slicing_enabled',
      return_value=(0, True),
  )
  mocker.patch(
      'xpk.commands.workload.get_installed_kueue_version',
      return_value=(1, None),
  )
  with pytest.raises(SystemExit):
    _validate_sub_slicing_availability()

  assert 'Unable to validate sub-slicing' in xpk_print.mock_calls[0].args[0]


def test_validate_sub_slicing_availability_exits_when_kueue_version_does_not_meet_minimum_requirements(
    xpk_print: MagicMock, mocker
):
  mocker.patch(
      'xpk.commands.workload.has_sub_slicing_enabled',
      return_value=(0, True),
  )
  mocker.patch(
      'xpk.commands.workload.get_installed_kueue_version',
      return_value=(0, Version('0.0.0')),
  )
  with pytest.raises(SystemExit):
    _validate_sub_slicing_availability()

  assert 'The minimal required version is' in xpk_print.mock_calls[0].args[0]


def test_validate_sub_slicing_availability_does_nothing_when_cluster_is_correctly_configured_for_subslicing(
    mocker,
):
  mocker.patch(
      'xpk.commands.workload.has_sub_slicing_enabled',
      return_value=(0, True),
  )
  mocker.patch(
      'xpk.commands.workload.get_installed_kueue_version',
      return_value=(0, Version('0.13.0')),
  )
  _validate_sub_slicing_availability()


@patch('xpk.commands.common.xpk_print')
def test_validate_sub_slicing_topology_fails_for_unsupported_system(
    common_xpk_print: MagicMock,
):
  unsupported_system = dataclasses.replace(
      SYSTEM_CHARACTERISTICS, supports_sub_slicing=False
  )

  with pytest.raises(SystemExit):
    _validate_sub_slicing_topology(unsupported_system, '4x4')

  assert (
      'l4-1 does not support Sub-slicing.'
      in common_xpk_print.mock_calls[0].args[0]
  )


def test_workload_create_for_a4x_has_arm_toleration(
    workload_create_mocks: _WorkloadCreateMocks,
):
  """Tests that the generated YAML for an A4X workload has arm64 toleration."""
  # Copy and overwrite the decorator with a no-op lambda.
  gb200_system_chars = UserFacingNameToSystemCharacteristics['gb200-4']
  gb200_system_chars_no_decorator = dataclasses.replace(
      gb200_system_chars,
      gpu_config=GpuConfig(
          requires_topology=False, jobset_decorator_fn=lambda yml, *_: yml
      ),
  )
  # Patch the function that returns the system characteristics
  # to return our modified object.
  with patch(
      'xpk.commands.workload.get_system_characteristics',
      return_value=(gb200_system_chars_no_decorator, 0),
  ):
    args = construct_args(
        device_type='gb200-4',
        workload='test-workload',
        command='echo hello',
        num_nodes=1,
        restart_on_exit_codes=None,
    )
    workload_create(args)

  assert workload_create_mocks.write_tmp_file.called
  yaml_content = workload_create_mocks.write_tmp_file.call_args[0][0]
  jobset = yaml.safe_load(yaml_content)

  tolerations = jobset['spec']['replicatedJobs'][0]['template']['spec'][
      'template'
  ]['spec']['tolerations']
  assert {
      'key': 'kubernetes.io/arch',
      'operator': 'Equal',
      'value': 'arm64',
      'effect': 'NoSchedule',
  } in tolerations
