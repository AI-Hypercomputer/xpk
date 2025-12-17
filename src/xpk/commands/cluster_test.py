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

import json
from argparse import Namespace
from dataclasses import dataclass
from typing import Any
from unittest.mock import MagicMock, patch
import pytest

from xpk.core.telemetry import MetricsCollector
from xpk.commands.cluster import _install_kueue, _validate_cluster_create_args, run_gke_cluster_create_command, cluster_create, _log_cluster_create_telemetry
from xpk.core.capacity import CapacityType
from xpk.core.system_characteristics import SystemCharacteristics, UserFacingNameToSystemCharacteristics
from xpk.core.testing.commands_tester import CommandsTester
from xpk.utils.feature_flags import FeatureFlags
from xpk.utils.versions import ReleaseChannel


@dataclass
class _Mocks:
  common_print_mock: MagicMock
  commands_print_mock: MagicMock
  commands_get_reservation_deployment_type: MagicMock
  commands_get_pathways_machine_types: MagicMock
  commands_tester: CommandsTester


@dataclass
class _ClusterCreateMocks:
  """Holds all the mocked dependencies for the cluster_create function."""

  get_all_clusters_programmatic: MagicMock
  get_gke_server_config: MagicMock
  get_gke_control_plane_version: MagicMock
  get_system_characteristics: MagicMock
  authorize_private_cluster_access_if_necessary: MagicMock
  update_coredns_if_necessary: MagicMock
  get_cluster_credentials: MagicMock
  setup_k8s_env: MagicMock
  get_gke_node_pool_version: MagicMock
  run_gke_node_pool_create_command: MagicMock
  create_cluster_configmaps: MagicMock
  set_jobset_on_cluster: MagicMock
  get_cluster_location: MagicMock
  xpk_exit: MagicMock
  update_jobset_resources_if_necessary: MagicMock
  _install_kueue: MagicMock
  set_pathways_job_on_cluster: MagicMock


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
  commands_get_pathways_machine_types = mocker.patch(
      'xpk.commands.cluster.get_pathways_machine_types',
      return_value=(0, []),
  )
  return _Mocks(
      common_print_mock=common_print_mock,
      commands_get_reservation_deployment_type=commands_get_reservation_deployment_type,
      commands_print_mock=commands_print_mock,
      commands_get_pathways_machine_types=commands_get_pathways_machine_types,
      commands_tester=CommandsTester(
          mocker,
          run_command_with_updates_path=(
              'xpk.commands.cluster.run_command_with_updates'
          ),
          run_command_for_value_path=(
              'xpk.commands.cluster.run_command_for_value'
          ),
      ),
  )


def construct_args(**kwargs: Any) -> Namespace:
  args_dict = dict(
      project='project',
      zone='us-central1-a',
      reservation='',
      on_demand=False,
      tpu_type=None,
      device_type=None,
      spot=False,
      default_pool_cpu_machine_type='test-machine-type',
      cluster='test-cluster',
      default_pool_cpu_num_nodes='100',
      sub_slicing=False,
      super_slicing=False,
      gke_version='',
      private=False,
      authorized_networks=None,
      pathways_gce_machine_type='n2-standard-64',
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
      create_vertex_tensorboard=False,
      enable_autoprovisioning=False,
      sub_slicing_topology='2x2x2',
      use_vertex_tensorboard=False,
      env_file='',
      env=None,
      use_pathways=False,
      debug_dump_gcs=False,
      storage='',
      restart_on_exit_codes=None,
      ttl_seconds_after_finished=0,
      max_restarts=1,
      priority=0,
      termination_grace_period_seconds=0,
      docker_image_pull_secret='',
      managed_mldiagnostics=False,
      output_manifest_file='',
  )
  args_dict.update(kwargs)
  return Namespace(**args_dict)


@pytest.fixture
def cluster_create_mocks(mocker) -> _ClusterCreateMocks:
  """Mocks all dependencies for the cluster_create function."""
  # This fixture patches all the functions called by cluster_create, allowing
  # tests to focus on specific logic paths without executing external commands
  # or complex sub-functions. Each mock can be configured within the test
  # itself if a specific return value or behavior is needed.
  return _ClusterCreateMocks(
      get_all_clusters_programmatic=mocker.patch(
          'xpk.commands.cluster.get_all_clusters_programmatic',
          return_value=([], 0),
      ),
      get_gke_server_config=mocker.patch(
          'xpk.commands.cluster.get_gke_server_config',
          return_value=(0, MagicMock()),
      ),
      get_gke_control_plane_version=mocker.patch(
          'xpk.commands.cluster.get_gke_control_plane_version'
      ),
      get_system_characteristics=mocker.patch(
          'xpk.commands.cluster.get_system_characteristics',
          return_value=(TPU_TEST_SYSTEM, 0),
      ),
      authorize_private_cluster_access_if_necessary=mocker.patch(
          'xpk.commands.cluster.authorize_private_cluster_access_if_necessary',
          return_value=0,
      ),
      update_coredns_if_necessary=mocker.patch(
          'xpk.commands.cluster.update_coredns_if_necessary', return_value=0
      ),
      get_cluster_credentials=mocker.patch(
          'xpk.commands.cluster.get_cluster_credentials', return_value=0
      ),
      setup_k8s_env=mocker.patch('xpk.commands.cluster.setup_k8s_env'),
      get_gke_node_pool_version=mocker.patch(
          'xpk.commands.cluster.get_gke_node_pool_version',
          return_value=(0, '1.2.3'),
      ),
      run_gke_node_pool_create_command=mocker.patch(
          'xpk.commands.cluster.run_gke_node_pool_create_command',
          return_value=0,
      ),
      create_cluster_configmaps=mocker.patch(
          'xpk.commands.cluster.create_cluster_configmaps', return_value=0
      ),
      set_jobset_on_cluster=mocker.patch(
          'xpk.commands.cluster.set_jobset_on_cluster', return_value=0
      ),
      get_cluster_location=mocker.patch(
          'xpk.commands.cluster.get_cluster_location',
          return_value='us-central1',
      ),
      xpk_exit=mocker.patch('xpk.commands.cluster.xpk_exit'),
      update_jobset_resources_if_necessary=mocker.patch(
          'xpk.commands.cluster.update_jobset_resources_if_necessary',
          return_value=0,
      ),
      _install_kueue=mocker.patch(
          'xpk.commands.cluster._install_kueue', return_value=0
      ),
      set_pathways_job_on_cluster=mocker.patch(
          'xpk.commands.cluster.set_pathways_job_on_cluster', return_value=0
      ),
  )


GPU_TEST_SYSTEM: SystemCharacteristics = UserFacingNameToSystemCharacteristics[
    'l4-1'
]
SUB_SLICING_SYSTEM: SystemCharacteristics = (
    UserFacingNameToSystemCharacteristics['v6e-4x4']
)
SUPER_SLICING_SYSTEM: SystemCharacteristics = (
    UserFacingNameToSystemCharacteristics['tpu7x-4x4x4']
)
TPU_TEST_SYSTEM: SystemCharacteristics = UserFacingNameToSystemCharacteristics[
    'v6e-4x4'
]


def test_validate_cluster_create_args_for_correct_args_pass(
    mocks: _Mocks,
):
  args = construct_args()

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


def test_validate_cluster_create_args_for_enable_pathways_set_to_false(
    mocks: _Mocks,
):
  args = construct_args(enable_pathways=False)
  mocks.commands_get_pathways_machine_types.return_value = (1, [])

  _validate_cluster_create_args(args, TPU_TEST_SYSTEM)

  assert mocks.commands_print_mock.call_count == 0


def test_validate_cluster_create_args_for_errored_pathways_machine_types_retrieval(
    mocks: _Mocks,
):
  args = construct_args(enable_pathways=True)
  mocks.commands_get_pathways_machine_types.return_value = (1, [])

  with pytest.raises(SystemExit):
    _validate_cluster_create_args(args, TPU_TEST_SYSTEM)

  assert mocks.commands_print_mock.call_count == 1
  assert 'Unable to retrieve' in mocks.commands_print_mock.call_args[0][0]


def test_validate_cluster_create_args_for_invalid_pathways_machine_type(
    mocks: _Mocks,
):
  args = construct_args(
      enable_pathways=True, pathways_gce_machine_type='n2-standard-32'
  )
  mocks.commands_get_pathways_machine_types.return_value = (
      0,
      ['n2-standard-64'],
  )

  with pytest.raises(SystemExit):
    _validate_cluster_create_args(args, TPU_TEST_SYSTEM)

  assert mocks.commands_print_mock.call_count == 2
  assert 'Available machine types' in mocks.commands_print_mock.call_args[0][0]


def test_validate_cluster_create_args_for_valid_pathways_machine_type(
    mocks: _Mocks,
):
  args = construct_args(
      enable_pathways=True, pathways_gce_machine_type='n2-standard-32'
  )
  mocks.commands_get_pathways_machine_types.return_value = (
      0,
      ['n2-standard-32'],
  )

  _validate_cluster_create_args(args, TPU_TEST_SYSTEM)

  assert mocks.commands_print_mock.call_count == 0


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
      release_channel=ReleaseChannel.STABLE,
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
      release_channel=ReleaseChannel.RAPID,
  )

  assert result == 0
  mocks.commands_tester.assert_command_not_run(
      'clusters create', ' --no-enable-autoupgrade'
  )
  mocks.commands_tester.assert_command_run(
      'clusters create', ' --release-channel=rapid'
  )


def test_run_gke_cluster_create_command_with_gke_version_has_no_autoupgrade_flag(
    mocks: _Mocks,
):
  result = run_gke_cluster_create_command(
      args=construct_args(gke_version='1.2.3'),
      gke_control_plane_version='1.2.3',
      system=TPU_TEST_SYSTEM,
      release_channel=ReleaseChannel.REGULAR,
  )

  assert result == 0
  mocks.commands_tester.assert_command_run(
      'clusters create', '--release-channel=regular', ' --no-enable-autoupgrade'
  )


def test_run_gke_cluster_create_command_with_lustre_runs_correct_command(
    mocks: _Mocks,
):
  result = run_gke_cluster_create_command(
      args=construct_args(
          enable_lustre_csi_driver=True, enable_legacy_lustre_port=False
      ),
      gke_control_plane_version='1.2.3',
      system=TPU_TEST_SYSTEM,
      release_channel=ReleaseChannel.REGULAR,
  )

  assert result == 0
  commands = mocks.commands_tester.get_matching_commands('clusters create')
  assert len(commands) == 1
  command = commands[0]
  assert (
      '--addons=LustreCsiDriver' in command
      and '--enable-legacy-lustre-port' not in command
  )


def test_run_gke_cluster_create_command_with_lustre_legacy_port_adds_correct_flag(
    mocks: _Mocks,
):
  result = run_gke_cluster_create_command(
      args=construct_args(
          enable_lustre_csi_driver=True, enable_legacy_lustre_port=True
      ),
      gke_control_plane_version='1.2.3',
      system=TPU_TEST_SYSTEM,
      release_channel=ReleaseChannel.REGULAR,
  )

  assert result == 0
  mocks.commands_tester.assert_command_run(
      'clusters create',
      '--enable-legacy-lustre-port',
      '--addons=LustreCsiDriver',
  )


def test_log_cluster_create_telemetry_does_not_log_when_feature_flag_is_disabled():
  FeatureFlags.TELEMETRY_ENABLED = False
  _log_cluster_create_telemetry(construct_args())
  events = json.loads(MetricsCollector.flush())['log_event']
  assert len(events) == 0


def test_log_cluster_create_telemetry_logs_correct_event_when_tpu_type_is_provided(
    mocker: MagicMock,
):
  FeatureFlags.TELEMETRY_ENABLED = True
  mocker.patch(
      'xpk.commands.cluster.get_capacity_type',
      return_value=(CapacityType.SPOT, 0),
  )
  _log_cluster_create_telemetry(construct_args(device_type='test-device-type'))
  event = json.loads(MetricsCollector.flush())['log_event'][0]
  payload = json.loads(event['source_extension_json'])
  event_metadata = payload['event_metadata']
  assert payload['event_name'] == 'cluster_create'
  assert (
      _get_event_metadata_value_by_key(
          event_metadata,
          'XPK_ZONE',
      )
      == 'us-central1-a'
  )
  assert (
      _get_event_metadata_value_by_key(
          event_metadata,
          'XPK_SYSTEM_CHARACTERISTICS',
      )
      == 'test-device-type'
  )
  assert (
      _get_event_metadata_value_by_key(
          event_metadata,
          'XPK_PROVISIONING_MODE',
      )
      == 'spot'
  )


def test_log_cluster_create_telemetry_logs_correct_event_when_device_type_is_provided(
    mocker: MagicMock,
):
  FeatureFlags.TELEMETRY_ENABLED = True
  mocker.patch(
      'xpk.commands.cluster.get_capacity_type',
      return_value=(CapacityType.SPOT, 0),
  )
  _log_cluster_create_telemetry(construct_args(tpu_type='test-tpu-type'))
  event = json.loads(MetricsCollector.flush())['log_event'][0]
  payload = json.loads(event['source_extension_json'])
  event_metadata = payload['event_metadata']
  assert payload['event_name'] == 'cluster_create'
  assert (
      _get_event_metadata_value_by_key(
          event_metadata,
          'XPK_ZONE',
      )
      == 'us-central1-a'
  )
  assert (
      _get_event_metadata_value_by_key(
          event_metadata,
          'XPK_SYSTEM_CHARACTERISTICS',
      )
      == 'test-tpu-type'
  )
  assert (
      _get_event_metadata_value_by_key(
          event_metadata,
          'XPK_PROVISIONING_MODE',
      )
      == 'spot'
  )


def _get_event_metadata_value_by_key(
    event_metadata: list[dict[str, str]], key: str
) -> str | None:
  return next(
      (meta['value'] for meta in event_metadata if meta['key'] == key),
      None,
  )


@pytest.mark.parametrize(
    'gke_version_arg, expected_channel, expected_version',
    [
        (None, ReleaseChannel.RAPID, '1.2.4'),  # No version, should use RAPID
        (
            '1.2.3',
            ReleaseChannel.REGULAR,
            '1.2.3',
        ),  # Version provided, should use REGULAR
    ],
)
def test_cluster_create_calls_run_command_with_correct_channel_and_version(
    gke_version_arg,
    expected_channel,
    expected_version,
    mocks: _Mocks,
    cluster_create_mocks: _ClusterCreateMocks,
):
  """
  Verifies that cluster_create calls run_gke_cluster_create_command with the correct
  release channel and GKE version based on whether a version is provided.
  """
  cluster_create_mocks.get_gke_control_plane_version.return_value = (
      0,
      expected_version,
  )

  args = construct_args(gke_version=gke_version_arg)
  cluster_create(args)

  expected_command_parts = [
      'clusters create',
      f'--cluster-version={expected_version}',
      f'--release-channel={expected_channel.value.lower()}',
  ]

  mocks.commands_tester.assert_command_run(*expected_command_parts)


def test_run_gke_cluster_create_command_with_super_slicing_enables_slice_controller(
    mocks: _Mocks,
):
  FeatureFlags.SUPER_SLICING_ENABLED = True
  result = run_gke_cluster_create_command(
      args=construct_args(gke_version='1.2.3', super_slicing=True),
      gke_control_plane_version='1.2.3',
      system=SUPER_SLICING_SYSTEM,
      release_channel=ReleaseChannel.REGULAR,
  )

  assert result == 0
  mocks.commands_tester.assert_command_run(
      'clusters create', '--enable-slice-controller'
  )


def test_validate_cluster_create_args_for_correct_super_slicing_args_pass(
    mocks: _Mocks,
):
  FeatureFlags.SUPER_SLICING_ENABLED = True
  args = construct_args(
      super_slicing=True,
      reservation='test-reservation/reservationBlocks/block',
      num_cubes=None,
      num_slices=None,
  )

  _validate_cluster_create_args(args, SUPER_SLICING_SYSTEM)
  args = construct_args(
      super_slicing=True,
      reservation='test-reservation/reservationBlocks/block/reservationSubBlocks/subblock',
      num_cubes=None,
      num_slices=None,
  )
  _validate_cluster_create_args(
      args, UserFacingNameToSystemCharacteristics['tpu7x-128']
  )

  assert mocks.common_print_mock.call_count == 0


def test_validate_cluster_create_args_for_super_slicing_system_not_supported_throws(
    mocks: _Mocks,
):
  FeatureFlags.SUPER_SLICING_ENABLED = True
  args = construct_args(
      super_slicing=True,
      reservation='test-reservation/reservationBlocks/block',
      num_cubes=None,
      num_slices=None,
  )

  with pytest.raises(SystemExit):
    _validate_cluster_create_args(
        args, UserFacingNameToSystemCharacteristics['tpu7x-4x4x8']
    )

  assert mocks.common_print_mock.call_count == 1
  assert (
      mocks.common_print_mock.call_args[0][0]
      == 'Error: tpu7x-256 does not support Super-slicing.'
  )


def test_validate_cluster_create_args_for_super_slicing_missing_reservation(
    mocks: _Mocks,
):
  FeatureFlags.SUPER_SLICING_ENABLED = True
  args = construct_args(
      super_slicing=True,
      reservation=None,
      num_cubes=None,
      num_slices=None,
  )

  with pytest.raises(SystemExit):
    _validate_cluster_create_args(args, SUPER_SLICING_SYSTEM)

  assert mocks.commands_print_mock.call_count == 1
  assert (
      'Validation failed: Super-slicing cluster creation requires'
      in mocks.commands_print_mock.call_args[0][0]
  )


def test_validate_cluster_create_args_for_super_slicing_reservation_no_blocks(
    mocks: _Mocks,
):
  FeatureFlags.SUPER_SLICING_ENABLED = True
  args = construct_args(
      super_slicing=True,
      reservation='reservation',
      num_cubes=None,
      num_slices=None,
  )

  with pytest.raises(SystemExit):
    _validate_cluster_create_args(args, SUPER_SLICING_SYSTEM)

  assert mocks.commands_print_mock.call_count == 1
  assert (
      'requires a block or sub-block reservation'
      in mocks.commands_print_mock.call_args[0][0]
  )


def test_validate_cluster_create_args_for_super_slicing_sparse_deployment_type_reservation(
    mocks: _Mocks,
):
  FeatureFlags.SUPER_SLICING_ENABLED = True
  args = construct_args(
      super_slicing=True,
      reservation='test-reservation/reservationBlocks/block',
      num_cubes=None,
      num_slices=None,
  )
  mocks.commands_get_reservation_deployment_type.return_value = 'SPARSE'

  with pytest.raises(SystemExit):
    _validate_cluster_create_args(args, SUPER_SLICING_SYSTEM)

  assert mocks.commands_print_mock.call_count == 5
  assert (
      'Refer to the documentation for more information on creating Cluster'
      in mocks.commands_print_mock.call_args[0][0]
  )


def test_validate_cluster_create_args_forbids_num_cubes_without_superslicing(
    mocks: _Mocks,
):
  FeatureFlags.SUPER_SLICING_ENABLED = True  # enable the feature
  args = construct_args(
      super_slicing=False,  # but disable the flag
      reservation='test-reservation/reservationBlocks/block',
      num_cubes=1,
      num_slices=None,
  )

  with pytest.raises(SystemExit):
    _validate_cluster_create_args(args, SUPER_SLICING_SYSTEM)

  assert mocks.commands_print_mock.call_count == 1
  assert (
      '--num-cubes can only be used with --super-slicing'
      in mocks.commands_print_mock.call_args[0][0]
  )


def test_validate_cluster_create_args_forbids_num_cubes_different_from_num_slices(
    mocks: _Mocks,
):
  FeatureFlags.SUPER_SLICING_ENABLED = True
  args = construct_args(
      super_slicing=True,
      reservation='test-reservation/reservationBlocks/block',
      num_cubes=1,
      num_slices=2,
  )

  with pytest.raises(SystemExit):
    _validate_cluster_create_args(args, SUPER_SLICING_SYSTEM)

  assert mocks.commands_print_mock.call_count == 1
  assert (
      '--num-cubes must not be different from --num-slices'
      in mocks.commands_print_mock.call_args[0][0]
  )


@pytest.mark.parametrize(
    'num_cubes, num_slices, expected',
    [
        (None, None, 1),
        (3, None, 3),
        (None, 3, 3),
        (3, 3, 3),
    ],
)
def test_validate_cluster_create_args_sets_correct_num_slices(
    mocks: _Mocks,
    num_cubes: int | None,
    num_slices: int | None,
    expected: int,
):
  FeatureFlags.SUPER_SLICING_ENABLED = True
  args = construct_args(
      super_slicing=True,
      reservation='test-reservation/reservationBlocks/block',
      num_cubes=num_cubes,
      num_slices=num_slices,
  )

  _validate_cluster_create_args(args, SUPER_SLICING_SYSTEM)

  assert args.num_slices == expected
