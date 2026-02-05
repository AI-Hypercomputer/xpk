"""
Copyright 2026 Google LLC

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
import pytest
from xpk.core.kubectl_common import PatchResources, patch_controller_manager_resources
from xpk.core.testing.commands_tester import CommandsTester


@pytest.fixture
def commands_tester(mocker):
  return CommandsTester(mocker)


def test_patch_controller_manager_resources_full(
    commands_tester: CommandsTester,
):
  result = patch_controller_manager_resources(
      name="name",
      namespace="namespace",
      replicas=7,
      patch_resources=PatchResources(
          cpu_request=1,
          cpu_limit=2,
          memory_request="10Gi",
          memory_limit="20Gi",
      ),
  )

  assert result == 0
  commands_tester.assert_command_run(
      "kubectl patch deployment", "name", "-n namespace"
  )
  expected_patch_dict = {
      "spec": {
          "replicas": 7,
          "template": {
              "spec": {
                  "containers": [{
                      "name": "manager",
                      "resources": {
                          "requests": {"cpu": "1", "memory": "10Gi"},
                          "limits": {"cpu": "2", "memory": "20Gi"},
                      },
                  }]
              }
          },
      }
  }
  commands_tester.assert_command_run(
      "kubectl patch", json.dumps(expected_patch_dict)
  )


def test_patch_controller_manager_resources_only_replicas(
    commands_tester: CommandsTester,
):
  result = patch_controller_manager_resources(
      name="name",
      namespace="namespace",
      replicas=7,
  )

  assert result == 0
  expected_patch_dict = {
      "spec": {
          "replicas": 7,
      }
  }
  commands_tester.assert_command_run(
      "kubectl patch", json.dumps(expected_patch_dict)
  )


def test_patch_controller_manager_resources_only_requests(
    commands_tester: CommandsTester,
):
  result = patch_controller_manager_resources(
      name="name",
      namespace="namespace",
      patch_resources=PatchResources(
          cpu_request=1,
          memory_request="10Gi",
      ),
  )

  assert result == 0
  commands_tester.assert_command_run(
      "kubectl patch deployment", "name", "-n namespace"
  )
  expected_patch_dict = {
      "spec": {
          "template": {
              "spec": {
                  "containers": [{
                      "name": "manager",
                      "resources": {
                          "requests": {"cpu": "1", "memory": "10Gi"},
                      },
                  }]
              }
          },
      }
  }
  commands_tester.assert_command_run(
      "kubectl patch", json.dumps(expected_patch_dict)
  )


def test_patch_controller_manager_resources_only_limits(
    commands_tester: CommandsTester,
):
  result = patch_controller_manager_resources(
      name="name",
      namespace="namespace",
      patch_resources=PatchResources(
          cpu_limit=2,
          memory_limit="20Gi",
      ),
  )

  assert result == 0
  commands_tester.assert_command_run(
      "kubectl patch deployment", "name", "-n namespace"
  )
  expected_patch_dict = {
      "spec": {
          "template": {
              "spec": {
                  "containers": [{
                      "name": "manager",
                      "resources": {
                          "limits": {"cpu": "2", "memory": "20Gi"},
                      },
                  }]
              }
          },
      }
  }
  commands_tester.assert_command_run(
      "kubectl patch", json.dumps(expected_patch_dict)
  )


def test_patch_controller_manager_resources_propagates_error(
    commands_tester: CommandsTester,
):
  commands_tester.set_result_for_command((123, "kubectl patch"))

  result = patch_controller_manager_resources(
      name="name",
      namespace="namespace",
      replicas=7,
  )

  assert result == 123
