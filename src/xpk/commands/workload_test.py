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

from ..core.scheduling import WorkloadScheduling
from ..core.system_characteristics import DockerPlatform, SystemCharacteristics, AcceleratorType, UserFacingNameToSystemCharacteristics, GpuConfig
from .workload import workload_create
from .cluster_test import construct_args
from ..core.docker_container import get_user_workload_container as real_get_user_workload_container


SYSTEM_CHARACTERISTICS = SystemCharacteristics(
    topology='8x8',
    vms_per_slice=1,
    gke_accelerator='nvidia-l4',
    gce_machine_type='g2-standard-12',
    chips_per_vm=1,
    accelerator_type=AcceleratorType.TPU,
    device_type='l4-1',
    supports_sub_slicing=True,
    supports_super_slicing=False,
    requires_workload_policy=False,
    supports_accelerator_network_profile=False,
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
  get_cluster_capacity_type: MagicMock
  is_TAS_possible: MagicMock
  get_cluster_location: MagicMock
  xpk_exit: MagicMock
  run_command_with_updates: MagicMock
  ensure_resource_policy_exists: MagicMock
  get_cluster_subnetworks: MagicMock


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
          return_value=WorkloadScheduling.AVAILABLE,
      ),
      setup_k8s_env=mocker.patch('xpk.commands.workload.setup_k8s_env'),
      setup_k8s_service_accounts=mocker.patch(
          'xpk.commands.workload.setup_k8s_service_accounts'
      ),
      validate_dependencies_list=mocker.patch(
          'xpk.commands.workload.validate_dependencies_list'
      ),
      write_tmp_file=mocker.patch('xpk.commands.workload.write_tmp_file'),
      get_cluster_capacity_type=mocker.patch(
          'xpk.commands.workload.get_cluster_capacity_type',
          return_value='on-demand',
      ),
      is_TAS_possible=mocker.patch(
          'xpk.commands.workload.is_TAS_possible', return_value=False
      ),
      get_cluster_location=mocker.patch(
          'xpk.commands.workload.get_cluster_location',
          return_value='us-central1',
      ),
      xpk_exit=mocker.patch('xpk.commands.workload.xpk_exit'),
      run_command_with_updates=mocker.patch(
          'xpk.commands.workload.run_command_with_updates', return_value=0
      ),
      ensure_resource_policy_exists=mocker.patch(
          'xpk.commands.workload.ensure_resource_policy_exists'
      ),
      get_cluster_subnetworks=mocker.patch(
          'xpk.commands.workload.get_cluster_subnetworks', return_value=[]
      ),
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


def test_workload_create_dry_run_with_output_file(mocker):
  args = MagicMock()
  args.workload = 'test-workload'
  args.output_manifest_file = 'manifest.yaml'
  args.use_pathways = False
  args.use_vertex_tensorboard = False
  args.project = 'test-project'
  args.cluster = 'test-cluster'
  args.zone = 'test-zone'
  args.sub_slicing_topology = None

  # Mock dependencies to avoid external calls and simulate state
  mocker.patch('xpk.utils.execution_context.dry_run', True)
  mocks = {
      'get_system_characteristics': (SYSTEM_CHARACTERISTICS, 0),
      'get_user_workload_container': ('container_yaml', None),
      'write_tmp_file': 'tmp_file',
      'parse_env_config': None,
  }
  for name, return_value in mocks.items():
    mocker.patch(f'xpk.commands.workload.{name}', return_value=return_value)

  mock_open = mocker.patch('builtins.open', mocker.mock_open())

  with pytest.raises(SystemExit):
    workload_create(args)

  mock_open.assert_called_once_with('manifest.yaml', 'w', encoding='utf-8')
  written_content = mock_open.return_value.write.call_args[0][0]
  assert 'test-workload' in written_content
  assert 'cloud.google.com/gke-tpu-topology: 8x8' in written_content


def test_workload_create_multi_container_for_tpu7x(
    workload_create_mocks: _WorkloadCreateMocks,
    mocker,
):
  """Tests that the generated YAML for a multi-container workload has correct pod failure policy and container structure."""

  # Enable dry_run to prevent external calls like get_storages_to_mount -> gcloud
  mocker.patch('xpk.utils.execution_context.dry_run', True)

  # Mock dependencies required by get_user_workload_container -> get_main_container
  mocker.patch(
      'xpk.core.docker_container.setup_docker_image',
      return_value=(0, 'dummy-image'),
  )
  mocker.patch(
      'xpk.core.docker_container.get_gke_debugging_dashboard', return_value=None
  )

  # Use the real get_user_workload_container to test integration
  workload_create_mocks.get_user_workload_container.side_effect = (
      real_get_user_workload_container
  )

  args = construct_args(
      workload='test-workload',
      command='echo hello',
      num_nodes=1,
      tpu_type='tpu7x-2x2x2',
      restart_on_exit_codes=None,
      docker_name='test-docker',
      deploy_stacktrace_sidecar=False,
      enable_debug_logs=False,
      scheduler='default-scheduler',
  )
  workload_create(args)

  assert workload_create_mocks.write_tmp_file.called
  yaml_content = workload_create_mocks.write_tmp_file.call_args[0][0]
  jobset = yaml.safe_load(yaml_content)

  # Verify Pod Failure Policy
  pod_failure_rules = jobset['spec']['replicatedJobs'][0]['template']['spec'][
      'podFailurePolicy'
  ]['rules']
  # Should have 2 rules for multi_container
  assert len(pod_failure_rules) == 2
  assert pod_failure_rules[0]['onExitCodes']['containerName'].endswith('-1')
  assert pod_failure_rules[1]['onExitCodes']['containerName'].endswith('-2')

  # Verify Containers
  # Navigate to the containers list in the YAML
  containers = jobset['spec']['replicatedJobs'][0]['template']['spec'][
      'template'
  ]['spec']['containers']

  assert len(containers) == 2
  assert containers[0]['name'].endswith('-1')
  assert containers[1]['name'].endswith('-2')
  assert containers[0]['image'] == 'dummy-image'
  assert containers[1]['image'] == 'dummy-image'

  # Check if resources are split correctly (4 chips / 2 containers = 2 chips)
  assert containers[0]['resources']['limits']['google.com/tpu'] == 2
  assert containers[1]['resources']['limits']['google.com/tpu'] == 2
