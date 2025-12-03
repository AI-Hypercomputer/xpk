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
import dataclasses
import pytest
from pytest_mock import MockerFixture
from xpk.core.capacity import AUTOPROVISIONING_CONFIG_MAXIMUM_KEY, AUTOPROVISIONING_CONFIG_VALUE
from xpk.core.testing.commands_tester import CommandsTester
from xpk.utils.feature_flags import FeatureFlags
from .scheduling import WorkloadScheduling, check_if_workload_can_schedule, create_sub_slicing_annotations, create_placement_policy_label, get_placement_policy_name, is_placement_policy_supported
from .system_characteristics import SystemCharacteristics, AcceleratorType, DockerPlatform, get_system_characteristics_by_device_type


def _get_system_characteristics_or_die(
    device_type: str,
) -> SystemCharacteristics:
  system = get_system_characteristics_by_device_type(device_type)[0]
  assert system
  return system


@pytest.fixture(autouse=True)
def commands_tester(mocker: MockerFixture) -> CommandsTester:
  return CommandsTester(
      mocker=mocker,
      run_command_for_value_path='xpk.core.kueue_manager.run_command_for_value',
  )


def test_create_sub_slicing_annotations_returns_valid_annotations():
  result = create_sub_slicing_annotations(sub_slicing_topology='2x4')

  assert result == [
      (
          'kueue.x-k8s.io/podset-required-topology:'
          ' "cloud.google.com/gke-tpu-slice-2x4-id"'
      ),
      'cloud.google.com/gke-tpu-slice-topology: 2x4',
  ]


def test_create_placement_policy_label_returns_valid_label():
  system_characteristics = SystemCharacteristics(
      chips_per_vm=1,
      gce_machine_type='tpu7x-standard-1t',
      gke_accelerator='tpu7x',
      requires_workload_policy=False,
      topology='1x1x1',
      vms_per_slice=1,
      device_type='tpu7x',
      accelerator_type=AcceleratorType.TPU,
      supports_sub_slicing=False,
      supports_super_slicing=False,
      docker_platform=DockerPlatform.ARM,
  )
  label = create_placement_policy_label(
      system_characteristics, super_slicing=False
  )
  assert (
      label
      == 'cloud.google.com/placement-policy-name: tpu7x-1x1x1-placement-policy'
  )


def test_get_placement_policy_name_returns_valid_name():
  system_characteristics = SystemCharacteristics(
      chips_per_vm=1,
      gce_machine_type='tpu7x-standard-1t',
      gke_accelerator='tpu7x',
      requires_workload_policy=False,
      topology='1x1x1',
      vms_per_slice=1,
      device_type='tpu7x',
      accelerator_type=AcceleratorType.TPU,
      supports_sub_slicing=False,
      supports_super_slicing=False,
      docker_platform=DockerPlatform.ARM,
  )
  name = get_placement_policy_name(system_characteristics, super_slicing=False)
  assert name == 'tpu7x-1x1x1-placement-policy'


def test_get_placement_policy_name_super_slicing_returns_valid_name():
  system_characteristics = SystemCharacteristics(
      chips_per_vm=1,
      gce_machine_type='tpu7x-standard-1t',
      gke_accelerator='tpu7x',
      requires_workload_policy=False,
      topology='1x1x1',
      vms_per_slice=1,
      device_type='tpu7x',
      accelerator_type=AcceleratorType.TPU,
      supports_sub_slicing=False,
      supports_super_slicing=False,
      docker_platform=DockerPlatform.ARM,
  )
  name = get_placement_policy_name(system_characteristics, super_slicing=True)
  assert name == 'tpu7x-1x1x1-ss-placement-policy'


def test_is_placement_policy_supported_returns_true_for_system_characteristics_supporting_workload_policy_and_having_valid_topology():
  system_characteristics = SystemCharacteristics(
      chips_per_vm=1,
      gce_machine_type='tpu7x-standard-1t',
      gke_accelerator='tpu7x',
      requires_workload_policy=True,
      topology='1x1x1',
      vms_per_slice=1,
      device_type='tpu7x',
      accelerator_type=AcceleratorType.TPU,
      supports_sub_slicing=False,
      supports_super_slicing=False,
      docker_platform=DockerPlatform.ARM,
  )
  assert is_placement_policy_supported(system_characteristics) is True


def test_is_placement_policy_supported_returns_false_for_system_characteristics_not_supporting_workload_policy_and_having_valid_topology():
  system_characteristics = SystemCharacteristics(
      chips_per_vm=1,
      gce_machine_type='tpu7x-standard-1t',
      gke_accelerator='tpu7x',
      requires_workload_policy=False,
      topology='1x1x1',
      vms_per_slice=1,
      device_type='tpu7x',
      accelerator_type=AcceleratorType.TPU,
      supports_sub_slicing=False,
      supports_super_slicing=False,
      docker_platform=DockerPlatform.ARM,
  )
  assert is_placement_policy_supported(system_characteristics) is False


def test_is_placement_policy_supported_returns_false_for_system_characteristics_supporting_workload_policy_and_having_invalid_topology():
  system_characteristics = SystemCharacteristics(
      chips_per_vm=1,
      gce_machine_type='tpu7x-standard-1t',
      gke_accelerator='tpu7x',
      requires_workload_policy=True,
      topology='aaa',
      vms_per_slice=1,
      device_type='tpu7x',
      accelerator_type=AcceleratorType.TPU,
      supports_sub_slicing=False,
      supports_super_slicing=False,
      docker_platform=DockerPlatform.ARM,
  )
  assert is_placement_policy_supported(system_characteristics) is False


@dataclass(frozen=True)
class SchedulingTestCase:
  workload_system: SystemCharacteristics
  num_slices: int = 1
  cluster_system: SystemCharacteristics | None = None
  resources_config_map: dict[str, str] | None = None
  kueue_version: str | None = None
  sub_slicing_feature_enabled: bool = False
  sub_slicing_topology_set: bool = False
  super_slicing_feature_enabled: bool = False
  super_slicing_topology_set: bool = False


NAP_CASE = SchedulingTestCase(
    workload_system=_get_system_characteristics_or_die('v6e-8'),
    cluster_system=None,
    resources_config_map={
        'tpu-v6e-slice': AUTOPROVISIONING_CONFIG_VALUE,
        AUTOPROVISIONING_CONFIG_MAXIMUM_KEY: '10',
    },
)

SUB_SLICING_CASE = SchedulingTestCase(
    workload_system=_get_system_characteristics_or_die('v6e-8'),
    cluster_system=_get_system_characteristics_or_die('v6e-16'),
    # 2 slices:
    resources_config_map={'v6e-16': str(8 // 4 * 2)},
    kueue_version='0.13.0',
    sub_slicing_feature_enabled=True,
    sub_slicing_topology_set=True,
    num_slices=1,
)

SUPER_SLICING_CASE = SchedulingTestCase(
    workload_system=_get_system_characteristics_or_die('tpu7x-4x4x16'),
    cluster_system=_get_system_characteristics_or_die('tpu7x-4x4x4'),
    # 5 4x4x4 cubes:
    resources_config_map={'tpu7x-128': str(64 // 4 * 5)},
    kueue_version='0.14.0',
    super_slicing_feature_enabled=True,
    super_slicing_topology_set=True,
    num_slices=1,
)


@pytest.mark.parametrize(
    'title, case, expected',
    [
        (
            'No resources config map',
            SchedulingTestCase(
                workload_system=_get_system_characteristics_or_die('v6e-8'),
                resources_config_map=None,
            ),
            WorkloadScheduling.AVAILABLE,
        ),
        (
            'Cluster system matches and workload fits',
            SchedulingTestCase(
                workload_system=_get_system_characteristics_or_die('v6e-8'),
                resources_config_map={'v6e-8': '8'},
                num_slices=2,
            ),
            WorkloadScheduling.AVAILABLE,
        ),
        (
            'Cluster system does not match',
            SchedulingTestCase(
                workload_system=_get_system_characteristics_or_die('v6e-8'),
                resources_config_map={'tpu7x-32': '16'},
            ),
            WorkloadScheduling.UNAVAILABLE,
        ),
        (
            'Workload does not fit',
            SchedulingTestCase(
                workload_system=_get_system_characteristics_or_die('v6e-8'),
                resources_config_map={'v6e-8': '8'},
                num_slices=100,
            ),
            WorkloadScheduling.UNAVAILABLE,
        ),
        (
            'Correct NAP',
            NAP_CASE,
            WorkloadScheduling.AVAILABLE,
        ),
        (
            'NAP, too big workload',
            dataclasses.replace(NAP_CASE, num_slices=100),
            WorkloadScheduling.UNAVAILABLE,
        ),
        (
            'Correct Sub-slicing',
            SUB_SLICING_CASE,
            WorkloadScheduling.SUB_SLICING_AVAILABLE,
        ),
        (
            'Sub-slicing, but disabled flag',
            dataclasses.replace(
                SUB_SLICING_CASE, sub_slicing_feature_enabled=False
            ),
            WorkloadScheduling.UNAVAILABLE,
        ),
        (
            'Sub-slicing, but low Kueue version',
            dataclasses.replace(SUB_SLICING_CASE, kueue_version='0.12.0'),
            WorkloadScheduling.UNAVAILABLE,
        ),
        (
            'Sub-slicing, but no sub-slicing-topology',
            dataclasses.replace(
                SUB_SLICING_CASE, sub_slicing_topology_set=False
            ),
            WorkloadScheduling.UNAVAILABLE,
        ),
        (
            'Sub-slicing, but workload too big',
            dataclasses.replace(SUB_SLICING_CASE, num_slices=100),
            WorkloadScheduling.UNAVAILABLE,
        ),
        (
            'Sub-slicing, but cluster system is incorrect',
            dataclasses.replace(
                SUB_SLICING_CASE,
                cluster_system=_get_system_characteristics_or_die('tpu7x-16'),
            ),
            WorkloadScheduling.UNAVAILABLE,
        ),
        (
            'Sub-slicing, but workload system is incorrect',
            dataclasses.replace(
                SUB_SLICING_CASE,
                workload_system=_get_system_characteristics_or_die('tpu7x-8'),
            ),
            WorkloadScheduling.UNAVAILABLE,
        ),
        (
            'Sub-slicing, but workload topology is incorrect',
            dataclasses.replace(
                SUB_SLICING_CASE,
                workload_system=_get_system_characteristics_or_die('v6e-2x2'),
            ),
            WorkloadScheduling.UNAVAILABLE,
        ),
        (
            (
                'Sub-slicing should be ignored when a given device is already'
                ' present in the cluster'
            ),
            dataclasses.replace(
                SUB_SLICING_CASE,
                workload_system=_get_system_characteristics_or_die('v6e-8'),
                cluster_system=_get_system_characteristics_or_die('v6e-8'),
                resources_config_map={'v6e-8': '4'},
            ),
            WorkloadScheduling.AVAILABLE,
        ),
        (
            'Correct Super-slicing',
            SUPER_SLICING_CASE,
            WorkloadScheduling.SUPER_SLICING_AVAILABLE,
        ),
        (
            'Super-slicing, but disabled flag',
            dataclasses.replace(
                SUPER_SLICING_CASE, super_slicing_feature_enabled=False
            ),
            WorkloadScheduling.UNAVAILABLE,
        ),
        (
            'Super-slicing, but low Kueue version',
            dataclasses.replace(SUPER_SLICING_CASE, kueue_version='0.13.0'),
            WorkloadScheduling.UNAVAILABLE,
        ),
        (
            'Super-slicing, but no super-slicing-topology',
            dataclasses.replace(
                SUPER_SLICING_CASE, super_slicing_topology_set=False
            ),
            WorkloadScheduling.UNAVAILABLE,
        ),
        (
            'Super-slicing, but workload too big',
            dataclasses.replace(SUPER_SLICING_CASE, num_slices=100),
            WorkloadScheduling.UNAVAILABLE,
        ),
        (
            'Super-slicing, but cluster system is incorrect',
            dataclasses.replace(
                SUPER_SLICING_CASE,
                cluster_system=_get_system_characteristics_or_die(
                    'tpu7x-4x4x8'
                ),
            ),
            WorkloadScheduling.UNAVAILABLE,
        ),
        (
            'Super-slicing, but workload system is incorrect',
            dataclasses.replace(
                SUPER_SLICING_CASE,
                workload_system=_get_system_characteristics_or_die('v6e-8'),
            ),
            WorkloadScheduling.UNAVAILABLE,
        ),
        (
            (
                'Super-slicing should be ignored when a given device is already'
                ' present in the cluster'
            ),
            dataclasses.replace(
                SUPER_SLICING_CASE,
                workload_system=_get_system_characteristics_or_die('tpu7x-64'),
                cluster_system=_get_system_characteristics_or_die('tpu7x-64'),
                resources_config_map={'tpu7x-64': '16'},
            ),
            WorkloadScheduling.AVAILABLE,
        ),
    ],
)
def test_check_if_workload_can_schedule(
    commands_tester: CommandsTester,
    title: str,
    case: SchedulingTestCase,
    expected: WorkloadScheduling,
):
  FeatureFlags.SUB_SLICING_ENABLED = case.sub_slicing_feature_enabled
  FeatureFlags.SUPER_SLICING_ENABLED = case.super_slicing_feature_enabled
  commands_tester.set_result_for_command(
      (
          0,
          f'registry.k8s.io/kueue/kueue:v{case.kueue_version}'
          if case.kueue_version
          else '',
      ),
      'kubectl get deployment',
      'image',
  )
  topology_response = ''
  if case.sub_slicing_topology_set:
    topology_response = 'sub-slice-topology'
  elif case.super_slicing_topology_set:
    topology_response = 'super-slice-topology'
  commands_tester.set_result_for_command(
      (0, topology_response),
      'kubectl get topology',
  )
  args = Namespace(
      cluster='test-cluster',
      workload='test-workload',
      num_slices=case.num_slices,
  )

  assert (
      check_if_workload_can_schedule(
          args,
          workload_system=case.workload_system,
          cluster_system=case.cluster_system,
          resources_config_map=case.resources_config_map,
      )
      == expected
  )
