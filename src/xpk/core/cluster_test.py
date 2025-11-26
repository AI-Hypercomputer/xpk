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
from .cluster import get_cluster_credentials, update_gke_cluster_with_lustre_driver_enabled, update_cluster_with_lustre_driver_if_necessary
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


def test_get_cluster_credentials_returns_1_when_retrieval_command_fails(
    commands_tester: CommandsTester, command_args
):
  commands_tester.set_result_for_command(
      (1, ""), "gcloud container clusters get-credentials"
  )
  assert get_cluster_credentials(command_args) == 1


def test_get_cluster_credentials_returns_0_when_retrieval_succeeds(
    commands_tester: CommandsTester, command_args
):
  commands_tester.set_result_for_command(
      (0, ""), "gcloud container clusters get-credentials"
  )
  assert get_cluster_credentials(command_args) == 0


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


def test_update_cluster_with_lustre_driver_if_necessary_with_default_port_runs_correct_checks(
    commands_tester: CommandsTester, command_args
):
  commands_tester.set_result_for_command(
      (0, "True"),
      "gcloud container clusters describe",
  )
  command_args.enable_legacy_lustre_port = None
  update_cluster_with_lustre_driver_if_necessary(command_args)

  executed_commands = commands_tester.get_matching_commands()
  assert executed_commands == [
      "gcloud container clusters describe cluster --project=project"
      " --location=us-central1"
      ' --format="value(addonsConfig.lustreCsiDriverConfig.enabled)"'
  ]


def test_update_cluster_with_lustre_driver_if_necessary_with_legacy_port_runs_correct_checks(
    commands_tester: CommandsTester, command_args
):
  commands_tester.set_result_for_command(
      (0, "True"),
      "gcloud container clusters describe",
  )
  command_args.enable_legacy_lustre_port = True
  update_cluster_with_lustre_driver_if_necessary(command_args)

  executed_commands = commands_tester.get_matching_commands()
  assert executed_commands == [
      (
          "gcloud container clusters describe cluster --project=project"
          " --location=us-central1"
          ' --format="value(addonsConfig.lustreCsiDriverConfig.enabled)"'
      ),
      (
          "gcloud container clusters describe cluster --project=project"
          " --location=us-central1"
          ' --format="value(addonsConfig.lustreCsiDriverConfig.enableLegacyLustrePort)"'
      ),
  ]


def test_update_gke_cluster_with_lustre_driver_enabled_default_port(
    commands_tester: CommandsTester, command_args
):
  commands_tester.set_result_for_command(
      (0, ""), "gcloud container clusters update"
  )
  command_args.enable_legacy_lustre_port = None
  update_gke_cluster_with_lustre_driver_enabled(command_args)

  executed_commands = commands_tester.get_matching_commands()
  assert executed_commands == [
      "gcloud container clusters update cluster --project=project"
      " --location=us-central1 --quiet --update-addons=LustreCsiDriver=ENABLED"
  ]


def test_update_gke_cluster_with_lustre_driver_enabled_legacy_port(
    commands_tester: CommandsTester, command_args
):
  commands_tester.set_result_for_command(
      (0, ""), "gcloud container clusters update"
  )
  command_args.enable_legacy_lustre_port = True
  update_gke_cluster_with_lustre_driver_enabled(command_args)

  executed_commands = commands_tester.get_matching_commands()
  assert executed_commands == [
      "gcloud container clusters update cluster --project=project"
      " --location=us-central1 --quiet --enable-legacy-lustre-port"
  ]
