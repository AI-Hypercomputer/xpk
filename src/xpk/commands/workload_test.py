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

from unittest.mock import MagicMock
import pytest
from ..core.system_characteristics import SystemCharacteristics, AcceleratorType
from .workload import workload_create


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
)


@pytest.fixture(autouse=True)
def xpk_print(mocker):
  return mocker.patch('xpk.commands.workload.xpk_print')


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
