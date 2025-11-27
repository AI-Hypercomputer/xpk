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
from unittest.mock import MagicMock
from xpk.core.testing.commands_tester import CommandsTester
from .pathways import get_pathways_machine_types


@pytest.fixture(autouse=True)
def commands_tester(mocker: MagicMock):
  return CommandsTester(
      mocker,
      run_command_with_updates_path=(
          "xpk.core.pathways.run_command_with_updates"
      ),
      run_command_for_value_path="xpk.core.pathways.run_command_for_value",
  )


def test_get_pathways_machine_types_when_command_fails_returns_failed_exit_code(
    commands_tester: CommandsTester,
):
  commands_tester.set_result_for_command(
      (1, ""), "gcloud compute machine-types list"
  )
  return_code, machine_types = get_pathways_machine_types(
      project="gke-project", zone="us-central1-a"
  )
  assert return_code == 1
  assert machine_types == []


def test_get_pathways_machine_types_when_command_suceeds_returns_machine_types(
    commands_tester: CommandsTester,
):
  commands_tester.set_result_for_command(
      (0, "abc\ncba"), "gcloud compute machine-types list"
  )
  return_code, machine_types = get_pathways_machine_types(
      project="gke-project", zone="us-central1-a"
  )
  assert return_code == 0
  assert machine_types == ["abc", "cba"]
