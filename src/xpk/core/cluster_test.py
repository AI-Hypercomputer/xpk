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
from .testing.commands_tester import CommandsTester
from .cluster import get_cluster_credentials
from pytest_mock import MockerFixture


@pytest.fixture(autouse=True)
def commands_tester(mocker: MockerFixture) -> CommandsTester:
  return CommandsTester(
      mocker=mocker,
      run_command_for_value_path="xpk.core.cluster.run_command_for_value",
      run_command_with_updates_path="xpk.core.cluster.run_command_with_updates",
  )


@pytest.fixture(autouse=True)
def mock_location(mocker: MockerFixture):
  mocker.patch(
      "xpk.core.cluster.get_cluster_location", return_value="us-central1"
  )


@pytest.fixture(autouse=True)
def command_args(mocker: MockerFixture):
  return mocker.Mock(cluster="cluster", project="project", zone="zone")


def test_get_cluster_credentials_does_not_retry_with_dns_when_retrieval_succeeds(
    commands_tester: CommandsTester, command_args
):
  commands_tester.set_result_for_command(
      (0, ""), "gcloud container clusters get-credentials --dns-endpoint"
  )
  commands_tester.set_result_for_command((0, ""), "kubectl get pods")
  get_cluster_credentials(command_args)
  non_dns_endpoint_commands = [
      c
      for c in commands_tester.get_matching_commands(
          "gcloud container clusters get-credentials"
      )
      if "dns-endpoint" not in c
  ]
  assert len(non_dns_endpoint_commands) == 0


def test_get_cluster_credentials_retries_without_dns_when_dns_retrieval_fails(
    commands_tester: CommandsTester, command_args
):
  commands_tester.set_result_for_command(
      (0, ""), "gcloud container clusters get-credentials --dns-endpoint"
  )
  commands_tester.set_result_for_command((1, ""), "kubectl get pods")
  get_cluster_credentials(command_args)
  non_dns_endpoint_commands = [
      c
      for c in commands_tester.get_matching_commands(
          "gcloud container clusters get-credentials"
      )
      if "dns-endpoint" not in c
  ]
  assert len(non_dns_endpoint_commands) == 1
