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
from packaging.version import Version
from pytest_mock import MockerFixture

from xpk.core.kueue_migrations import install_kueue_manifest_upgrading
from xpk.core.testing.commands_tester import CommandsTester

SAMPLE_0_14_0_MIGRATION_COMMAND = (
    "kubectl get topologies.kueue.x-k8s.io -o yaml"
)
""" Part of the command unique to the v.0.14.0 migration."""


@pytest.fixture(autouse=True)
def mock_make_tmp_file(mocker: MockerFixture):
  mocker.patch(
      "xpk.core.kueue_migrations.make_tmp_file",
      wraps=lambda prefix: f"{prefix}.yaml",
  )


@pytest.fixture(autouse=True)
def mock_commands(mocker: MockerFixture) -> CommandsTester:
  return CommandsTester(
      mocker,
      run_command_for_value_path=(
          "xpk.core.kueue_migrations.run_command_for_value"
      ),
      run_command_with_updates_retry_path=(
          "xpk.core.kueue_migrations.run_command_with_updates_retry"
      ),
  )


def test_install_kueue_manifest_upgrading_from_empty_version(
    mock_commands: CommandsTester,
):
  return_code = install_kueue_manifest_upgrading(
      from_version=None, to_version=Version("v1.0.0")
  )

  assert return_code == 0
  assert len(mock_commands.commands_history) == 1
  mock_commands.assert_command_run("kubectl apply", "v1.0.0/manifests.yaml")


def test_install_kueue_manifest_upgrading_with_successful_migration_returns_0():
  return_code = install_kueue_manifest_upgrading(
      from_version=Version("v0.13.0"), to_version=Version("v0.14.2")
  )

  assert return_code == 0


def test_install_kueue_manifest_upgrading_with_failed_installation_returns_1(
    mock_commands: CommandsTester,
):
  mock_commands.set_result_for_command(
      (1, ""), "kubectl apply", "v1.0.0/manifests.yaml"
  )

  return_code = install_kueue_manifest_upgrading(
      from_version=None, to_version=Version("v1.0.0")
  )

  assert return_code == 1


def test_install_kueue_manifest_upgrading_with_failed_migration_breaks_upgrade_flow(
    mock_commands: CommandsTester,
):
  mock_commands.set_result_for_command((1, ""), SAMPLE_0_14_0_MIGRATION_COMMAND)

  return_code = install_kueue_manifest_upgrading(
      from_version=Version("v0.13.0"), to_version=Version("v0.14.1")
  )

  mock_commands.assert_command_not_run("kubectl apply", "manifests.yaml")
  assert return_code == 1


def test_install_kueue_manifest_upgrading_from_breaking_version_skips_that_version(
    mock_commands: CommandsTester,
):
  install_kueue_manifest_upgrading(
      from_version=Version("v0.13.0"), to_version=Version("v0.14.0")
  )

  assert len(mock_commands.commands_history) > 0
  mock_commands.assert_command_not_run(
      "kubectl apply", "v0.13.0/manifests.yaml"
  )


def test_install_kueue_manifest_upgrading_to_breaking_version_installs_it_once(
    mock_commands: CommandsTester,
):
  install_kueue_manifest_upgrading(
      from_version=Version("v0.13.0"), to_version=Version("v0.14.0")
  )

  mock_commands.assert_command_run("kubectl apply", "v0.14.0/manifests.yaml")


def test_install_kueue_manifest_upgrading_to_breaking_version_performs_migration(
    mock_commands: CommandsTester,
):
  install_kueue_manifest_upgrading(
      from_version=Version("v0.13.0"), to_version=Version("v0.14.0")
  )

  mock_commands.assert_command_run(SAMPLE_0_14_0_MIGRATION_COMMAND)


def test_install_kueue_manifest_upgrading_to_old_version_skips_newer_migration(
    mock_commands: CommandsTester,
):
  install_kueue_manifest_upgrading(
      from_version=Version("v0.13.0"), to_version=Version("v0.13.5")
  )

  mock_commands.assert_command_not_run(SAMPLE_0_14_0_MIGRATION_COMMAND)
  mock_commands.assert_command_run("kubectl apply", "v0.13.5/manifests.yaml")


def test_install_kueue_manifest_upgrading_from_0_12_to_0_14_2_installs_3_versions_in_order(
    mock_commands: CommandsTester,
):
  install_kueue_manifest_upgrading(
      from_version=Version("v0.12.0"), to_version=Version("v0.14.2")
  )

  matching_commands = mock_commands.get_matching_commands(
      "kubectl apply", "/manifests.yaml"
  )
  assert len(matching_commands) == 3
  assert "v0.13.0" in matching_commands[0]
  assert "v0.14.0" in matching_commands[1]
  assert "v0.14.2" in matching_commands[2]


def test_install_kueue_manifest_upgrading_0_13_0_migration(
    mock_commands: CommandsTester,
):
  install_kueue_manifest_upgrading(
      from_version=Version("v0.12.0"), to_version=Version("v0.13.0")
  )

  # Runs 3 pre-install commands:
  assert (
      mock_commands.commands_history[0]
      == "kubectl get cohorts.kueue.x-k8s.io -o yaml > cohorts.yaml"
  )
  assert (
      "sed -i -e 's/v1alpha1/v1beta1/g' cohorts.yaml sed -i"
      in mock_commands.commands_history[1]
  )
  assert (
      mock_commands.commands_history[2]
      == "kubectl delete crd cohorts.kueue.x-k8s.io"
  )

  # Installation:
  assert "download/v0.13.0/manifests.yaml" in mock_commands.commands_history[3]

  # Runs 1 post-install commands:
  assert mock_commands.commands_history[4] == "kubectl apply -f cohorts.yaml"


def test_install_kueue_manifest_upgrading_0_14_0_migration(
    mock_commands: CommandsTester,
):
  install_kueue_manifest_upgrading(
      from_version=Version("v0.13.0"), to_version=Version("v0.14.0")
  )

  # Runs 4 pre-install commands:
  assert (
      mock_commands.commands_history[0]
      == "kubectl get topologies.kueue.x-k8s.io -o yaml > topologies.yaml"
  )
  assert (
      "sed -i -e 's/v1alpha1/v1beta1/g' topologies.yaml"
      in mock_commands.commands_history[1]
  )
  assert (
      mock_commands.commands_history[2]
      == "kubectl delete crd topologies.kueue.x-k8s.io"
  )
  assert (
      "kubectl get topology.kueue.x-k8s.io -o jsonpath="
      in mock_commands.commands_history[3]
  )

  # Installation:
  assert "download/v0.14.0/manifests.yaml" in mock_commands.commands_history[4]

  # Runs 1 post-install commands:
  assert mock_commands.commands_history[5] == "kubectl apply -f topologies.yaml"
