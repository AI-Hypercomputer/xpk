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


from xpk.core.kubectl_common import parse_kubernetes_status, KubernetesStatus


def test_parse_kubernetes_status():
  test_dict = {
      "conditions": [
          {
              "type": "Ready",
              "status": "True",
              "lastTransitionTime": "2023-01-01T00:00:00Z",
              "message": "All good",
          },
          {"type": "Test", "status": "", "lastTransitionTime": None},
      ]
  }
  status = parse_kubernetes_status(test_dict)
  assert isinstance(status, KubernetesStatus)
  assert len(status.conditions) == 2

  assert status.conditions[0].type == "Ready"
  assert status.conditions[0].status == "True"
  assert status.conditions[0].lastTransitionTime == "2023-01-01T00:00:00Z"
  assert status.conditions[0].message == "All good"

  assert status.conditions[1].type == "Test"
  assert status.conditions[1].status is None
  assert status.conditions[1].lastTransitionTime is None
  assert status.conditions[1].message is None


def test_parse_kubernetes_status_empty():
  status = parse_kubernetes_status(None)
  assert isinstance(status, KubernetesStatus)
  assert len(status.conditions) == 0

  status2 = parse_kubernetes_status({})
  assert isinstance(status2, KubernetesStatus)
  assert len(status2.conditions) == 0

  status3 = parse_kubernetes_status({"conditions": None})
  assert isinstance(status3, KubernetesStatus)
  assert len(status3.conditions) == 0


from xpk.core.kubectl_common import is_managed_externally


def test_is_managed_externally_true(commands_tester: CommandsTester):
  commands_tester.set_result_for_command((0, "Helm"))
  return_code, is_external = is_managed_externally("name", "namespace")
  assert return_code == 0
  assert is_external is True
  commands_tester.assert_command_run(
      "kubectl get deployment name -n namespace -o"
      r" jsonpath='{.metadata.labels.app\.kubernetes\.io/managed-by}'"
  )


def test_is_managed_externally_true_other_manager(
    commands_tester: CommandsTester,
):
  commands_tester.set_result_for_command((
      0,
      "kustomize",
  ))
  return_code, is_external = is_managed_externally("name", "namespace")
  assert return_code == 0
  assert is_external is True


def test_is_managed_externally_false(commands_tester: CommandsTester):
  commands_tester.set_result_for_command((
      0,
      "",
  ))
  return_code, is_external = is_managed_externally("name", "namespace")
  assert return_code == 0
  assert is_external is False


def test_is_managed_externally_command_error(commands_tester: CommandsTester):
  commands_tester.set_result_for_command((1, "error"))
  return_code, is_helm = is_managed_externally("name", "namespace")
  assert return_code == 1
  assert is_helm is None
