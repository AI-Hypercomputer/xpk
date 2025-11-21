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

from dataclasses import dataclass
from unittest.mock import MagicMock
import pytest
from xpk.commands.managed_ml_diagnostics import install_mldiagnostics_prerequisites
from xpk.core.testing.commands_tester import CommandsTester


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
              'xpk.commands.managed_ml_diagnostics.run_command_with_updates'
          ),
          run_command_for_value_path=(
              'xpk.commands.managed_ml_diagnostics.run_command_for_value'
          ),
      ),
  )


def test_install_mldiagnostics_prerequisites_commands_executed(
    mocks: _Mocks,
):

  install_mldiagnostics_prerequisites()

  mocks.commands_tester.assert_command_run(
      'kubectl',
      'rollout',
      'status',
      'deployment/kueue-controller-manager',
      times=1,
  )

  mocks.commands_tester.assert_command_run(
      'kubectl',
      'apply',
      '-f',
      'https://github.com/cert-manager/cert-manager/',
      times=1,
  )

  mocks.commands_tester.assert_command_run(
      'kubectl', 'rollout', 'status', 'deployment/cert-manager-webhook', times=1
  )

  mocks.commands_tester.assert_command_run(
      'gcloud',
      'artifacts',
      'generic',
      'download',
      '--package=mldiagnostics-injection-webhook',
      '--version=v0.5.0',
      times=1,
  )

  mocks.commands_tester.assert_command_run(
      'kubectl', 'create', 'namespace', 'gke-mldiagnostics', times=1
  )

  mocks.commands_tester.assert_command_run(
      'kubectl',
      'apply',
      '-f',
      '/tmp/mldiagnostics-injection-webhook-v0.5.0.yaml',
      '-n',
      'gke-mldiagnostics',
      times=1,
  )

  mocks.commands_tester.assert_command_run(
      'kubectl',
      'label',
      'namespace',
      'default',
      'managed-mldiagnostics-gke=true',
      times=1,
  )

  mocks.commands_tester.assert_command_run(
      'gcloud',
      'artifacts',
      'generic',
      'download',
      '--package=mldiagnostics-connection-operator',
      '--version=v0.5.0',
      times=1,
  )

  mocks.commands_tester.assert_command_run(
      'kubectl',
      'apply',
      '-f',
      '/tmp/mldiagnostics-connection-operator-v0.5.0.yaml',
      '-n',
      'gke-mldiagnostics',
      times=1,
  )

  mocks.commands_tester.assert_command_run(
      'gcloud', 'artifacts', 'generic', 'download', times=2
  )

  mocks.commands_tester.assert_command_run(
      'kubectl', 'apply', '-f', '-n', 'gke-mldiagnostics', times=2
  )
