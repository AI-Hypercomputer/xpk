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

import dataclasses
from typing import Generator, TypeVar
import pytest
from pytest_mock import MockerFixture
import yaml
from unittest.mock import MagicMock, patch

from xpk.core.kueue_manager import KueueConfig, KueueManager, has_sub_slicing_enabled, has_super_slicing_enabled
from xpk.core.system_characteristics import GpuConfig, DockerPlatform, AcceleratorType, SystemCharacteristics, UserFacingNameToSystemCharacteristics
from xpk.core.testing.commands_tester import CommandsTester
from packaging.version import Version

TPU_SYSTEM: SystemCharacteristics = SystemCharacteristics(
    topology="2x2x1",
    vms_per_slice=1,
    gke_accelerator="test-accelerator",
    gce_machine_type="test-machine",
    chips_per_vm=4,
    accelerator_type=AcceleratorType.TPU,
    device_type="v5p-8",
    supports_sub_slicing=False,
    supports_super_slicing=False,
    docker_platform=DockerPlatform.ARM,
)

KUEUE_CONFIG: KueueConfig = KueueConfig(
    system=TPU_SYSTEM,
    total_chips=8,
    cpu_limit=100,
    memory_limit="100Gi",
    configure_sub_slicing=False,
    configure_super_slicing=False,
)


def set_installed_kueue_version(
    commands_tester: CommandsTester, version: Version | None
):
  result = (
      (1, "")
      if version is None
      else (0, f"registry.k8s.io/kueue/kueue:v{version}")
  )
  commands_tester.set_result_for_command(
      result,
      "kubectl get deployment kueue-controller-manager",
      "containers[0].image",
  )


@pytest.fixture(autouse=True)
def mock_ask_for_user_consent(mocker: MockerFixture) -> MagicMock:
  return mocker.patch(
      "xpk.core.kueue_manager.ask_for_user_consent", return_value=True
  )


@pytest.fixture(autouse=True)
def mock_commands(mocker: MockerFixture) -> CommandsTester:
  return CommandsTester(
      mocker,
      run_command_for_value_path="xpk.core.kueue_manager.run_command_for_value",
      run_command_with_updates_path=(
          "xpk.core.kueue_manager.run_command_with_updates"
      ),
      run_command_with_updates_retry_path=(
          "xpk.core.kueue_manager.run_command_with_updates_retry"
      ),
  )


@pytest.fixture(autouse=True)
@patch("jinja2.Environment", return_value=MagicMock())
def kueue_manager(mock_env: MagicMock) -> KueueManager:
  return KueueManager("test-project", "test-zone")


def test_install_or_upgrade_when_newer_version_already_installed(
    mock_commands: CommandsTester, kueue_manager: KueueManager
):
  """Test install_or_upgrade when Kueue is already up to date."""
  set_installed_kueue_version(mock_commands, Version("0.99.0"))

  result = kueue_manager.install_or_upgrade(KUEUE_CONFIG)

  assert result == 0
  mock_commands.assert_command_not_run("kubectl apply")


def test_install_or_upgrade_when_outdated(
    mock_commands: CommandsTester, kueue_manager: KueueManager
):
  """Test install_or_upgrade when an older version of Kueue is installed."""
  set_installed_kueue_version(mock_commands, Version("0.11.0"))

  result = kueue_manager.install_or_upgrade(KUEUE_CONFIG)

  assert result == 0
  mock_commands.assert_command_run("kubectl apply", "v0.14.3/manifests.yaml")
  mock_commands.assert_command_run("kubectl apply -f", "/tmp/")


def test_install_or_upgrade_when_not_installed(
    mock_commands: CommandsTester, kueue_manager: KueueManager
):
  """Test install_or_upgrade when Kueue is not installed."""
  set_installed_kueue_version(mock_commands, None)

  result = kueue_manager.install_or_upgrade(KUEUE_CONFIG)

  assert result == 0
  mock_commands.assert_command_run("kubectl apply", "v0.14.3/manifests.yaml")
  mock_commands.assert_command_run("kubectl apply -f", "/tmp/")


def test_upgrade_when_no_breaking_changes_between_versions_no_preparation_needed(
    mock_commands: CommandsTester,
    kueue_manager: KueueManager,
    mock_ask_for_user_consent: MagicMock,
):
  set_installed_kueue_version(mock_commands, Version("0.14.0"))

  kueue_manager.install_or_upgrade(KUEUE_CONFIG)

  mock_ask_for_user_consent.assert_not_called()


def test_upgrade_with_breaking_changes_between_versions_runs_preparation(
    mock_commands: CommandsTester,
    kueue_manager: KueueManager,
    mock_ask_for_user_consent: MagicMock,
):
  set_installed_kueue_version(mock_commands, Version("0.11.0"))
  fake_crds = (
      "customresourcedefinition.apiextensions.k8s.io/kueue-crd-1.kueue.x-k8s.io\n"
      "customresourcedefinition.apiextensions.k8s.io/kueue-crd-2.kueue.x-k8s.io"
  )
  mock_commands.set_result_for_command(
      (0, fake_crds), "kubectl get crd -o name"
  )
  mock_ask_for_user_consent.return_value = True

  result = kueue_manager.install_or_upgrade(KUEUE_CONFIG)

  assert result == 0
  mock_ask_for_user_consent.assert_called_once()
  assert (
      "CHANGELOG/CHANGELOG-0.14.md"
      in mock_ask_for_user_consent.mock_calls[0].args[0]
  )
  mock_commands.assert_command_run(
      "kubectl delete kueue-crd-1.kueue.x-k8s.io --all"
  )
  mock_commands.assert_command_run(
      "kubectl delete kueue-crd-2.kueue.x-k8s.io --all"
  )
  mock_commands.assert_command_run(
      "kubectl delete crd kueue-crd-1.kueue.x-k8s.io"
  )
  mock_commands.assert_command_run(
      "kubectl delete crd kueue-crd-2.kueue.x-k8s.io"
  )
  mock_commands.assert_command_run(
      "kubectl delete deployment kueue-controller-manager"
  )


def test_upgrade_with_breaking_changes_between_versions_does_not_run_preparation_without_consent(
    mock_commands: CommandsTester,
    kueue_manager: KueueManager,
    mock_ask_for_user_consent: MagicMock,
):
  set_installed_kueue_version(mock_commands, Version("0.11.0"))
  mock_commands.set_result_for_command(
      (
          0,
          "customresourcedefinition.apiextensions.k8s.io/kueue-crd-1.kueue.x-k8s.io",
      ),
      "kubectl get crd -o name",
  )
  mock_ask_for_user_consent.return_value = False

  result = kueue_manager.install_or_upgrade(KUEUE_CONFIG)

  assert result == 1
  # Assert there was no command run for the Kueue crd:
  mock_commands.assert_command_not_run("kueue-crd-1.kueue.x-k8s.io")


def test_installation_with_tolerations(
    mock_commands: CommandsTester, kueue_manager: KueueManager
):
  """Test that tolerations are patched during installation."""
  set_installed_kueue_version(mock_commands, None)
  tolerations = [{"key": "test", "operator": "Exists", "effect": "NoSchedule"}]

  result = kueue_manager.install_or_upgrade(
      KUEUE_CONFIG, tolerations=tolerations
  )

  assert result == 0
  mock_commands.assert_command_run(
      "kubectl patch deployment kueue-controller-manager -n kueue-system"
      ' --type=\'strategic\' --patch=\'{"spec": {"template": {"spec":'
      ' {"tolerations": [{"key": "test", "operator": "Exists", "effect":'
      ' "NoSchedule"}]}}}}\''
  )


def test_installation_without_tolerations(
    mock_commands: CommandsTester, kueue_manager: KueueManager
):
  """Test that tolerations are not patched when not provided."""
  set_installed_kueue_version(mock_commands, None)

  result = kueue_manager.install_or_upgrade(KUEUE_CONFIG, tolerations=None)

  assert result == 0
  mock_commands.assert_command_not_run(
      "kubectl patch deployment kueue-controller-manager", "tolerations"
  )


def test_resource_update_for_small_cluster(
    mock_commands: CommandsTester, kueue_manager: KueueManager
):
  """Test resource update logic for a small cluster."""
  set_installed_kueue_version(mock_commands, None)
  mock_commands.set_result_for_command((0, "100"), "kubectl get node")

  result = kueue_manager.install_or_upgrade(KUEUE_CONFIG)

  assert result == 0
  # 100 * 1.2 = 120, which is less than 4096. So it should be 4096.
  mock_commands.assert_command_run(
      "kubectl patch deployment kueue-controller-manager -n kueue-system"
      ' --type=\'strategic\' --patch=\'{"spec": {"template": {"spec":'
      ' {"containers": [{"name": "manager", "resources": {"limits":'
      ' {"memory": "4096Mi"}}}]}}}}\'',
  )


def test_resource_update_for_large_cluster(
    mock_commands: CommandsTester, kueue_manager: KueueManager
):
  """Test resource update logic for a large cluster."""
  set_installed_kueue_version(mock_commands, None)
  mock_commands.set_result_for_command((0, "5000"), "kubectl get node")

  result = kueue_manager.install_or_upgrade(KUEUE_CONFIG)

  assert result == 0
  # 5000 * 1.2 = 6000, which is > 4096.
  mock_commands.assert_command_run(
      "kubectl patch deployment kueue-controller-manager -n kueue-system"
      ' --type=\'strategic\' --patch=\'{"spec": {"template": {"spec":'
      ' {"containers": [{"name": "manager", "resources": {"limits":'
      ' {"memory": "6000Mi"}}}]}}}}\'',
  )


@patch("xpk.core.kueue_manager.write_tmp_file")
def test_configure_generates_correct_manifest_for_tpu(
    write_tmp_file_mock: MagicMock,
    mock_commands: CommandsTester,
    kueue_manager: KueueManager,
):
  """Test that __configure generates the correct manifest content for TPUs."""
  set_installed_kueue_version(mock_commands, None)
  mock_commands.set_result_for_command(
      (0, "100 102400"), "gcloud compute machine-types describe"
  )

  tpu_kueue_config = dataclasses.replace(
      KUEUE_CONFIG, system=TPU_SYSTEM, num_slices=2
  )

  kueue_manager.install_or_upgrade(tpu_kueue_config)

  rendered_manifest: str = write_tmp_file_mock.call_args[0][0]
  assert "kind: Topology" not in rendered_manifest
  manifest_docs = list(yaml.safe_load_all(rendered_manifest))
  cluster_queue = _first(
      doc for doc in manifest_docs if doc["kind"] == "ClusterQueue"
  )
  assert (
      cluster_queue["spec"]["resourceGroups"][0]["flavors"][0]["name"]
      == "2xv5p-8"
  )
  resources = cluster_queue["spec"]["resourceGroups"][0]["flavors"][0][
      "resources"
  ]
  tpu_resource = _first(r for r in resources if r["name"] == "google.com/tpu")
  cpu_resource = _first(r for r in resources if r["name"] == "cpu")
  memory_resource = _first(r for r in resources if r["name"] == "memory")
  assert tpu_resource["nominalQuota"] == 8
  assert cpu_resource["nominalQuota"] == 100
  assert memory_resource["nominalQuota"] == "100Gi"
  resource_flavor = _first(
      doc for doc in manifest_docs if doc["kind"] == "ResourceFlavor"
  )
  assert (
      resource_flavor["spec"]["nodeLabels"][
          "cloud.google.com/gke-tpu-accelerator"
      ]
      == "test-accelerator"
  )
  assert (
      resource_flavor["spec"]["nodeLabels"]["cloud.google.com/gke-tpu-topology"]
      == "2x2x1"
  )


@patch("xpk.core.kueue_manager.write_tmp_file")
def test_install_autocorrects_resource_limits(
    write_tmp_file_mock: MagicMock,
    mock_commands: CommandsTester,
    kueue_manager: KueueManager,
):
  """Test that installation auto-corrects the specified resource limits."""
  set_installed_kueue_version(mock_commands, None)
  # set 50 vCPU, 200Gi memory
  mock_commands.set_result_for_command(
      (0, "50 204800"), "gcloud compute machine-types describe"
  )

  kueue_config = dataclasses.replace(
      KUEUE_CONFIG, cpu_limit=100, memory_limit="100Gi"
  )

  kueue_manager.install_or_upgrade(kueue_config)

  rendered_manifest: str = write_tmp_file_mock.call_args[0][0]
  manifest_docs = list(yaml.safe_load_all(rendered_manifest))
  cluster_queue = _first(
      doc for doc in manifest_docs if doc["kind"] == "ClusterQueue"
  )
  resources = cluster_queue["spec"]["resourceGroups"][0]["flavors"][0][
      "resources"
  ]
  cpu_resource = _first(r for r in resources if r["name"] == "cpu")
  memory_resource = _first(r for r in resources if r["name"] == "memory")
  assert cpu_resource["nominalQuota"] == 50
  assert memory_resource["nominalQuota"] == "204800Mi"


@patch("xpk.core.kueue_manager.write_tmp_file")
def test_configure_generates_manifest_with_admission_checks_for_flex_single_slice(
    write_tmp_file_mock: MagicMock,
    mock_commands: CommandsTester,
    kueue_manager: KueueManager,
):
  """Test that __configure generates the correct manifest with admission checks."""
  set_installed_kueue_version(mock_commands, None)
  kueue_config = dataclasses.replace(
      KUEUE_CONFIG,
      num_slices=1,
      flex=True,
      system=UserFacingNameToSystemCharacteristics["l4-1"],
  )

  kueue_manager.install_or_upgrade(kueue_config)

  rendered_manifest: str = write_tmp_file_mock.call_args[0][0]
  assert "kind: Topology" not in rendered_manifest
  manifest_docs = list(yaml.safe_load_all(rendered_manifest))
  cluster_queue = _first(
      doc for doc in manifest_docs if doc["kind"] == "ClusterQueue"
  )
  assert (
      cluster_queue["spec"]["resourceGroups"][0]["flavors"][0]["name"]
      == "1xl4-1"
  )
  assert cluster_queue["spec"]["admissionChecks"][0] == "dws-prov"


@patch("xpk.core.kueue_manager.write_tmp_file")
def test_configure_generates_correct_manifest_with_gke_default_topology(
    write_tmp_file_mock: MagicMock,
    mock_commands: CommandsTester,
    kueue_manager: KueueManager,
):
  """Test that __configure generates correct manifest for GPUs."""
  set_installed_kueue_version(mock_commands, None)
  kueue_config = dataclasses.replace(
      KUEUE_CONFIG,
      system=SystemCharacteristics(
          topology="2x2x1",
          vms_per_slice=1,
          gke_accelerator="h100-mega-80gb-8",
          gce_machine_type="a3-megagpu-8g",
          chips_per_vm=8,
          accelerator_type=AcceleratorType.GPU,
          device_type="h100-mega-80gb-8",
          supports_sub_slicing=False,
          supports_super_slicing=False,
          docker_platform=DockerPlatform.ARM,
          gpu_config=GpuConfig(requires_topology=True),
      ),
  )

  kueue_manager.install_or_upgrade(kueue_config)

  rendered_manifest: str = write_tmp_file_mock.call_args[0][0]
  manifest_docs = list(yaml.safe_load_all(rendered_manifest))
  resource_flavor = _first(
      doc for doc in manifest_docs if doc["kind"] == "ResourceFlavor"
  )
  assert (
      resource_flavor["spec"]["nodeLabels"]["cloud.google.com/gke-accelerator"]
      == "h100-mega-80gb-8"
  )
  assert resource_flavor["spec"]["topologyName"] == "gke-default"
  topology = _first(doc for doc in manifest_docs if doc["kind"] == "Topology")
  assert topology["metadata"]["name"] == "gke-default"


@patch("xpk.core.kueue_manager.write_tmp_file")
def test_configure_generates_correct_manifest_with_sub_slicing(
    write_tmp_file_mock: MagicMock,
    mock_commands: CommandsTester,
    kueue_manager: KueueManager,
):
  """Test that __configure generates correct manifest with sub-slicing topology."""
  set_installed_kueue_version(mock_commands, None)
  kueue_config = dataclasses.replace(
      KUEUE_CONFIG,
      configure_sub_slicing=True,
      system=UserFacingNameToSystemCharacteristics["v6e-8x8"],
  )

  kueue_manager.install_or_upgrade(kueue_config)

  rendered_manifest: str = write_tmp_file_mock.call_args[0][0]
  manifest_docs = list(yaml.safe_load_all(rendered_manifest))
  resource_flavor = _first(
      doc for doc in manifest_docs if doc["kind"] == "ResourceFlavor"
  )
  assert resource_flavor["spec"]["topologyName"] == "sub-slice-topology"
  topology = _first(doc for doc in manifest_docs if doc["kind"] == "Topology")
  assert topology["metadata"]["name"] == "sub-slice-topology"
  expected_levels = [
      "cloud.google.com/gke-tpu-slice-8x8-id",
      "cloud.google.com/gke-tpu-slice-4x8-id",
      "cloud.google.com/gke-tpu-slice-4x4-id",
      "cloud.google.com/gke-tpu-slice-2x4-id",
      "kubernetes.io/hostname",
  ]
  actual_levels = [level["nodeLabel"] for level in topology["spec"]["levels"]]
  assert actual_levels == expected_levels


@patch("xpk.core.kueue_manager.write_tmp_file")
def test_configure_generates_correct_manifest_with_super_slicing(
    write_tmp_file_mock: MagicMock,
    mock_commands: CommandsTester,
    kueue_manager: KueueManager,
):
  """Test that __configure generates correct manifest with super-slicing topology."""
  set_installed_kueue_version(mock_commands, None)
  kueue_config = dataclasses.replace(
      KUEUE_CONFIG,
      configure_super_slicing=True,
      system=UserFacingNameToSystemCharacteristics["tpu7x-4x4x4"],
  )

  kueue_manager.install_or_upgrade(kueue_config)

  rendered_manifest: str = write_tmp_file_mock.call_args[0][0]
  manifest_docs = list(yaml.safe_load_all(rendered_manifest))
  resource_flavor = _first(
      doc for doc in manifest_docs if doc["kind"] == "ResourceFlavor"
  )
  assert resource_flavor["spec"]["topologyName"] == "super-slice-topology"
  assert resource_flavor["spec"]["nodeLabels"] == {
      "cloud.google.com/gke-tpu-accelerator": "tpu7x",
      "cloud.google.com/gke-tpu-partition-4x4x4-state": "HEALTHY",
  }
  topology = _first(doc for doc in manifest_docs if doc["kind"] == "Topology")
  assert topology["metadata"]["name"] == "super-slice-topology"
  expected_levels = [
      "cloud.google.com/gce-topology-block",
      "cloud.google.com/gke-tpu-partition-4x4x4-id",
      "kubernetes.io/hostname",
  ]
  actual_levels = [level["nodeLabel"] for level in topology["spec"]["levels"]]
  assert actual_levels == expected_levels
  cluster_queue = _first(
      doc for doc in manifest_docs if doc["kind"] == "ClusterQueue"
  )
  assert cluster_queue["spec"]["admissionChecks"][0] == "ss-kueue-operator"


@patch("xpk.core.kueue_manager.write_tmp_file")
def test_configure_generates_correct_manifest_with_pathways(
    write_tmp_file_mock: MagicMock,
    mock_commands: CommandsTester,
    kueue_manager: KueueManager,
):
  """Test that __configure generates the correct manifest with pathways enabled."""
  set_installed_kueue_version(mock_commands, None)
  kueue_config = dataclasses.replace(
      KUEUE_CONFIG,
      is_pathways_cluster=True,
  )

  kueue_manager.install_or_upgrade(kueue_config)

  rendered_manifest: str = write_tmp_file_mock.call_args[0][0]
  manifest_docs = list(yaml.safe_load_all(rendered_manifest))

  # Check for the new "cpu-user" ResourceFlavor
  cpu_user_flavor = _first(
      doc
      for doc in manifest_docs
      if doc["kind"] == "ResourceFlavor"
      and doc["metadata"]["name"] == "cpu-user"
  )
  assert (
      cpu_user_flavor["spec"]["nodeLabels"]["cloud.google.com/gke-nodepool"]
      == "cpu-np"
  )

  # Check that the ClusterQueue has the new resource group for pathways
  cluster_queue = _first(
      doc for doc in manifest_docs if doc["kind"] == "ClusterQueue"
  )
  assert len(cluster_queue["spec"]["resourceGroups"]) == 2
  pathways_rg = cluster_queue["spec"]["resourceGroups"][1]
  assert pathways_rg["coveredResources"] == ["cpu", "memory"]
  assert pathways_rg["flavors"][0]["name"] == "cpu-user"
  assert pathways_rg["flavors"][0]["resources"][0]["nominalQuota"] == 480
  assert pathways_rg["flavors"][0]["resources"][1]["nominalQuota"] == "2000G"


@patch("xpk.core.kueue_manager.write_tmp_file")
def test_configure_generates_correct_manifest_for_a4x(
    write_tmp_file_mock: MagicMock,
    mock_commands: CommandsTester,
    kueue_manager: KueueManager,
):
  """Test that __configure generates correct manifest for a4x GPUs."""
  set_installed_kueue_version(mock_commands, None)
  kueue_config = dataclasses.replace(
      KUEUE_CONFIG,
      system=UserFacingNameToSystemCharacteristics["gb200-4"],
  )

  kueue_manager.install_or_upgrade(kueue_config)

  rendered_manifest: str = write_tmp_file_mock.call_args[0][0]
  manifest_docs = list(yaml.safe_load_all(rendered_manifest))

  # Check that the gke-default topology is present for a4x.
  topology = _first(doc for doc in manifest_docs if doc["kind"] == "Topology")
  assert topology["metadata"]["name"] == "gke-default"


def test_has_sub_slicing_enabled_returns_exit_code_when_command_fails(
    mock_commands: CommandsTester,
):
  mock_commands.set_result_for_command((1, ""), "kubectl get topology")

  return_code, result = has_sub_slicing_enabled()

  assert return_code == 1
  assert result is None


def test_has_sub_slicing_enabled_returns_false_when_sub_slicing_topology_is_not_present(
    mock_commands: CommandsTester,
):
  mock_commands.set_result_for_command((0, ""), "kubectl get topology")

  return_code, result = has_sub_slicing_enabled()

  assert return_code == 0
  assert result is False


def test_has_sub_slicing_enabled_returns_true_when_sub_slicing_topology_is_present(
    mock_commands: CommandsTester,
):
  mock_commands.set_result_for_command(
      (0, "sub-slice-topology"), "kubectl get topology"
  )

  return_code, result = has_sub_slicing_enabled()

  assert return_code == 0
  assert result is True


def test_has_super_slicing_enabled_returns_exit_code_when_command_fails(
    mock_commands: CommandsTester,
):
  mock_commands.set_result_for_command((1, ""), "kubectl get topology")

  return_code, result = has_super_slicing_enabled()

  assert return_code == 1
  assert result is None


def test_has_super_slicing_enabled_returns_false_when_super_slicing_topology_is_not_present(
    mock_commands: CommandsTester,
):
  mock_commands.set_result_for_command((0, ""), "kubectl get topology")

  return_code, result = has_super_slicing_enabled()

  assert return_code == 0
  assert result is False


def test_has_super_slicing_enabled_returns_true_when_super_slicing_topology_is_present(
    mock_commands: CommandsTester,
):
  mock_commands.set_result_for_command(
      (0, "super-slice-topology"), "kubectl get topology"
  )

  return_code, result = has_super_slicing_enabled()

  assert return_code == 0
  assert result is True


T = TypeVar("T")


def _first(generator: Generator[T, None, None]) -> T:
  result = next(generator, None)
  assert result is not None
  return result
