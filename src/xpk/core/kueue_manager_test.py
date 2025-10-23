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

from typing import Generator, TypeVar
import unittest
import yaml
from unittest.mock import MagicMock, patch

from xpk.core.kueue_manager import KueueConfig, KueueManager
from xpk.core.system_characteristics import AcceleratorType, SystemCharacteristics


class KueueManagerTest(unittest.TestCase):
  """Unit tests for the KueueManager class."""

  def setUp(self):
    """Set up test environment."""
    self.mock_system_chars_gpu = SystemCharacteristics(
        topology="2x2x1",
        vms_per_slice=1,
        gke_accelerator="h100-mega-80gb-8",
        gce_machine_type="a3-megagpu-8g",
        chips_per_vm=8,
        accelerator_type=AcceleratorType["GPU"],
        device_type="h100-mega-80gb-8",
        supports_sub_slicing=False,
    )

    self.mock_system_chars = SystemCharacteristics(
        topology="2x2x1",
        vms_per_slice=1,
        gke_accelerator="test-accelerator",
        gce_machine_type="test-machine",
        chips_per_vm=4,
        accelerator_type=AcceleratorType["TPU"],
        device_type="v5p-8",
        supports_sub_slicing=False,
    )
    mock_env = MagicMock()

    with patch("jinja2.Environment", return_value=mock_env):
      self.kueue_manager = KueueManager()

  @patch("xpk.core.kueue_manager.run_command_for_value")
  def test_version_check_when_kueue_not_installed(self, mock_run_for_value):
    mock_run_for_value.return_value = (
        0,
        "Kueue deployment does not exist error message",
    )
    kueue_config = MagicMock(spec=KueueConfig)

    with (
        patch.object(
            self.kueue_manager, "_KueueManager__install", return_value=0
        ) as mock_install,
        patch.object(
            self.kueue_manager, "_KueueManager__configure", return_value=0
        ) as mock_configure,
    ):
      result = self.kueue_manager.install_or_upgrade(kueue_config)

      self.assertEqual(result, 0)
      mock_install.assert_called_once()
      mock_configure.assert_called_once()

  @patch("xpk.core.kueue_manager.KueueManager.get_installed_kueue_version")
  @patch("xpk.core.kueue_manager.KueueManager._KueueManager__install")
  @patch("xpk.core.kueue_manager.KueueManager._KueueManager__configure")
  def test_install_or_upgrade_when_newer_version_already_installed(
      self, mock_configure, mock_install, mock_get_version
  ):
    """Test install_or_upgrade when Kueue is already up to date."""
    mock_get_version.return_value = (0, "v0.99.9")
    kueue_config = MagicMock(spec=KueueConfig)

    result = self.kueue_manager.install_or_upgrade(kueue_config)

    self.assertEqual(result, 0)
    mock_get_version.assert_called_once()
    mock_install.assert_not_called()
    mock_configure.assert_not_called()

  @patch("xpk.core.kueue_manager.KueueManager.get_installed_kueue_version")
  def test_install_or_upgrade_when_outdated(
      self,
      mock_get_version,
  ):
    """Test install_or_upgrade when an older version of Kueue is installed."""
    mock_get_version.return_value = (0, "v0.11.0")
    kueue_config = MagicMock(spec=KueueConfig)

    with (
        patch.object(
            self.kueue_manager, "_KueueManager__install", return_value=0
        ) as mock_install,
        patch.object(
            self.kueue_manager, "_KueueManager__configure", return_value=0
        ) as mock_configure,
    ):
      result = self.kueue_manager.install_or_upgrade(kueue_config)

    self.assertEqual(result, 0)
    mock_get_version.assert_called_once()
    mock_install.assert_called_once()
    mock_configure.assert_called_once()

  @patch("xpk.core.kueue_manager.KueueManager.get_installed_kueue_version")
  def test_install_or_upgrade_when_not_installed(
      self,
      mock_get_version,
  ):
    """Test install_or_upgrade when Kueue is not installed."""
    mock_get_version.return_value = (1, None)
    kueue_config = MagicMock(spec=KueueConfig)

    with (
        patch.object(
            self.kueue_manager, "_KueueManager__install", return_value=0
        ) as mock_install,
        patch.object(
            self.kueue_manager, "_KueueManager__configure", return_value=0
        ) as mock_configure,
    ):
      result = self.kueue_manager.install_or_upgrade(kueue_config)

    self.assertEqual(result, 0)
    mock_get_version.assert_called_once()
    mock_install.assert_called_once()
    mock_configure.assert_called_once()

  def test_installation_with_tolerations(self):
    """Test that tolerations are patched during installation."""
    with (
        patch(
            "xpk.core.kueue_manager.run_command_with_updates_retry",
            return_value=0,
        ) as mock_run_retry,
        patch(
            "xpk.core.kueue_manager.KueueManager.get_installed_kueue_version",
            return_value=(1, None),
        ),
        patch(
            "xpk.core.kueue_manager.KueueManager._KueueManager__install_kueue_crs",
            return_value=0,
        ),
        patch(
            "xpk.core.kueue_manager.KueueManager._KueueManager__wait_for_kueue_available",
            return_value=0,
        ),
        patch(
            "xpk.core.kueue_manager.KueueManager._KueueManager__configure",
            return_value=0,
        ),
    ):
      tolerations = [
          {"key": "test", "operator": "Exists", "effect": "NoSchedule"}
      ]
      kueue_config = MagicMock(spec=KueueConfig)

      result = self.kueue_manager.install_or_upgrade(
          kueue_config, tolerations=tolerations
      )

      self.assertEqual(result, 0)
      self.assertEqual(mock_run_retry.call_count, 1)
      patch_call = mock_run_retry.call_args_list[0]
      self.assertIn(
          "kubectl patch deployment kueue-controller-manager -n kueue-system"
          ' --type=\'strategic\' --patch=\'{"spec": {"template": {"spec":'
          ' {"tolerations": [{"key": "test", "operator": "Exists", "effect":'
          ' "NoSchedule"}]}}}}',
          patch_call[0][0],
      )

  def test_installation_without_tolerations(self):
    """Test that tolerations are not patched when not provided."""
    with (
        patch(
            "xpk.core.kueue_manager.run_command_with_updates_retry",
            return_value=0,
        ) as mock_run_retry,
        patch(
            "xpk.core.kueue_manager.KueueManager.get_installed_kueue_version",
            return_value=(1, None),
        ),
        patch(
            "xpk.core.kueue_manager.KueueManager._KueueManager__install_kueue_crs",
            return_value=0,
        ),
        patch(
            "xpk.core.kueue_manager.KueueManager._KueueManager__wait_for_kueue_available",
            return_value=0,
        ),
        patch(
            "xpk.core.kueue_manager.KueueManager._KueueManager__configure",
            return_value=0,
        ),
    ):
      kueue_config = MagicMock(spec=KueueConfig)

      result = self.kueue_manager.install_or_upgrade(
          kueue_config, tolerations=None
      )

      self.assertEqual(result, 0)
      self.assertEqual(mock_run_retry.call_count, 0)

  @patch("xpk.core.kueue_manager.KueueManager.get_installed_kueue_version")
  @patch("xpk.core.kueue_manager.KueueManager._KueueManager__apply_manifest")
  def test_configuration_updates_resources(
      self, mock_apply_manifest, mock_get_version
  ):
    """Test that configuration updates Kueue resources."""
    mock_get_version.return_value = (1, None)  # Trigger install
    mock_apply_manifest.return_value = 0

    kueue_config = KueueConfig(
        system=self.mock_system_chars,
        total_chips=8,
        cpu_limit=100,
        memory_limit="100Gi",
        configure_sub_slicing=False,
    )

    with (
        patch.object(
            self.kueue_manager, "_KueueManager__install", return_value=0
        ),
        patch.object(
            self.kueue_manager,
            "_KueueManager__update_kueue_resources_if_necessary",
            return_value=0,
        ) as mock_update_resources,
    ):
      self.kueue_manager.install_or_upgrade(kueue_config)
      mock_apply_manifest.assert_called()
      mock_update_resources.assert_called_once()

  @patch("xpk.core.kueue_manager.run_command_with_updates_retry")
  def test_resource_update_for_small_cluster(self, mock_run_retry):
    """Test resource update logic for a small cluster."""
    mock_run_retry.return_value = 0
    kueue_config = KueueConfig(
        system=self.mock_system_chars,
        total_chips=8,
        cpu_limit=100,
        memory_limit="100Gi",
        configure_sub_slicing=False,
    )

    with (
        patch(
            "xpk.core.kueue_manager.run_command_for_value",
            return_value=(0, "100"),  # 100 nodes
        ),
        patch.object(
            self.kueue_manager,
            "get_installed_kueue_version",
            return_value=(1, None),
        ),
        patch.object(
            self.kueue_manager, "_KueueManager__install", return_value=0
        ),
        patch.object(
            self.kueue_manager, "_KueueManager__apply_manifest", return_value=0
        ),
    ):
      result = self.kueue_manager.install_or_upgrade(kueue_config)

    self.assertEqual(result, 0)
    mock_run_retry.assert_called_once()
    patch_call = mock_run_retry.call_args_list[0]
    # 100 * 1.2 = 120, which is less than 4096. So it should be 4096.
    self.assertIn(
        "kubectl patch deployment kueue-controller-manager -n kueue-system"
        ' --type=\'strategic\' --patch=\'{"spec": {"template": {"spec":'
        ' {"containers": [{"name": "manager", "resources": {"limits":'
        ' {"memory": "4096Mi"}}}]}}}}\'',
        patch_call[0][0],
    )

  @patch("xpk.core.kueue_manager.run_command_with_updates_retry")
  def test_resource_update_for_large_cluster(self, mock_run_retry):
    """Test resource update logic for a large cluster."""
    mock_run_retry.return_value = 0
    kueue_config = KueueConfig(
        system=self.mock_system_chars,
        total_chips=8,
        cpu_limit=100,
        memory_limit="100Gi",
        configure_sub_slicing=False,
    )

    with (
        patch(
            "xpk.core.kueue_manager.run_command_for_value",
            return_value=(0, "5000"),  # 5000 nodes
        ),
        patch.object(
            self.kueue_manager,
            "get_installed_kueue_version",
            return_value=(1, None),
        ),
        patch.object(
            self.kueue_manager, "_KueueManager__install", return_value=0
        ),
        patch.object(
            self.kueue_manager, "_KueueManager__apply_manifest", return_value=0
        ),
    ):
      result = self.kueue_manager.install_or_upgrade(kueue_config)

    self.assertEqual(result, 0)
    mock_run_retry.assert_called_once()
    patch_call = mock_run_retry.call_args_list[0]
    # 5000 * 1.2 = 6000, which is > 4096.
    self.assertIn(
        "kubectl patch deployment kueue-controller-manager -n kueue-system"
        ' --type=\'strategic\' --patch=\'{"spec": {"template": {"spec":'
        ' {"containers": [{"name": "manager", "resources": {"limits":'
        ' {"memory": "6000Mi"}}}]}}}}\'',
        patch_call[0][0],
    )

  @patch("xpk.core.kueue_manager.KueueManager._KueueManager__install")
  @patch(
      "xpk.core.kueue_manager.KueueManager._KueueManager__update_kueue_resources_if_necessary"
  )
  def test_configure_generates_correct_manifest_for_tpu(
      self, mock_update_resources, mock_install
  ):
    """Test that __configure generates the correct manifest content for TPUs."""
    mock_install.return_value = 0
    mock_update_resources.return_value = 0
    kueue_config = KueueConfig(
        system=self.mock_system_chars,
        total_chips=8,
        cpu_limit=100,
        memory_limit="100Gi",
        autoprovisioning_enabled=False,
        num_slices=2,
        configure_sub_slicing=False,
    )

    rendered_manifest = self._trigger_installation(kueue_config)

    self.assertNotIn("kind: Topology", rendered_manifest)
    manifest_docs = list(yaml.safe_load_all(rendered_manifest))
    cluster_queue = _first(
        doc for doc in manifest_docs if doc["kind"] == "ClusterQueue"
    )
    self.assertEqual(
        cluster_queue["spec"]["resourceGroups"][0]["flavors"][0]["name"],
        "2xv5p-8",
    )
    resources = cluster_queue["spec"]["resourceGroups"][0]["flavors"][0][
        "resources"
    ]
    tpu_resource = _first(r for r in resources if r["name"] == "google.com/tpu")
    cpu_resource = _first(r for r in resources if r["name"] == "cpu")
    memory_resource = _first(r for r in resources if r["name"] == "memory")
    self.assertEqual(tpu_resource["nominalQuota"], 8)
    self.assertEqual(cpu_resource["nominalQuota"], 100)
    self.assertEqual(memory_resource["nominalQuota"], "100Gi")
    resource_flavor = _first(
        doc for doc in manifest_docs if doc["kind"] == "ResourceFlavor"
    )
    self.assertEqual(
        resource_flavor["spec"]["nodeLabels"][
            "cloud.google.com/gke-tpu-accelerator"
        ],
        "test-accelerator",
    )
    self.assertEqual(
        resource_flavor["spec"]["nodeLabels"][
            "cloud.google.com/gke-tpu-topology"
        ],
        "2x2x1",
    )

  @patch("xpk.core.kueue_manager.KueueManager._KueueManager__install")
  @patch(
      "xpk.core.kueue_manager.KueueManager._KueueManager__update_kueue_resources_if_necessary"
  )
  def test_configure_generates_manifest_with_admission_checks_for_flex_single_slice(
      self, mock_update_resources, mock_install
  ):
    """Test that __configure generates the correct manifest with admission checks."""
    mock_install.return_value = 0
    mock_update_resources.return_value = 0
    kueue_config = KueueConfig(
        system=self.mock_system_chars,
        total_chips=8,
        cpu_limit=100,
        memory_limit="100Gi",
        autoprovisioning_enabled=False,
        num_slices=1,
        flex=True,
        configure_sub_slicing=False,
    )

    rendered_manifest = self._trigger_installation(kueue_config)

    self.assertNotIn("kind: Topology", rendered_manifest)
    manifest_docs = list(yaml.safe_load_all(rendered_manifest))
    cluster_queue = _first(
        doc for doc in manifest_docs if doc["kind"] == "ClusterQueue"
    )
    self.assertEqual(
        cluster_queue["spec"]["resourceGroups"][0]["flavors"][0]["name"],
        "1xv5p-8",
    )
    self.assertEqual(cluster_queue["spec"]["admissionChecks"][0], "dws-prov")

  @patch("xpk.core.kueue_manager.KueueManager._KueueManager__install")
  @patch(
      "xpk.core.kueue_manager.KueueManager._KueueManager__update_kueue_resources_if_necessary"
  )
  def test_configure_generates_correct_manifest_with_gke_default_topology(
      self, mock_update_resources, mock_install
  ):
    """Test that __configure generates correct manifest for GPUs."""
    mock_install.return_value = 0
    mock_update_resources.return_value = 0
    kueue_config = KueueConfig(
        system=self.mock_system_chars_gpu,
        total_chips=16,
        cpu_limit=100,
        memory_limit="100Gi",
        num_slices=2,
        configure_sub_slicing=False,
    )

    rendered_manifest = self._trigger_installation(kueue_config)

    manifest_docs = list(yaml.safe_load_all(rendered_manifest))
    resource_flavor = _first(
        doc for doc in manifest_docs if doc["kind"] == "ResourceFlavor"
    )
    self.assertEqual(
        resource_flavor["spec"]["nodeLabels"][
            "cloud.google.com/gke-accelerator"
        ],
        "h100-mega-80gb-8",
    )
    self.assertEqual(resource_flavor["spec"]["topologyName"], "gke-default")
    topology = _first(doc for doc in manifest_docs if doc["kind"] == "Topology")
    self.assertEqual(topology["metadata"]["name"], "gke-default")

  @patch("xpk.core.kueue_manager.KueueManager._KueueManager__install")
  @patch(
      "xpk.core.kueue_manager.KueueManager._KueueManager__update_kueue_resources_if_necessary"
  )
  def test_configure_generates_correct_manifest_with_sub_slicing(
      self, mock_update_resources, mock_install
  ):
    """Test that __configure generates correct manifest with sub-slicing topology."""
    mock_install.return_value = 0
    mock_update_resources.return_value = 0
    kueue_config = KueueConfig(
        system=self.mock_system_chars,
        total_chips=16,
        cpu_limit=100,
        memory_limit="100Gi",
        num_slices=2,
        configure_sub_slicing=True,
    )

    rendered_manifest = self._trigger_installation(kueue_config)

    manifest_docs = list(yaml.safe_load_all(rendered_manifest))
    resource_flavor = _first(
        doc for doc in manifest_docs if doc["kind"] == "ResourceFlavor"
    )
    self.assertEqual(
        resource_flavor["spec"]["topologyName"], "sub-slice-topology"
    )
    topology = _first(doc for doc in manifest_docs if doc["kind"] == "Topology")
    self.assertEqual(topology["metadata"]["name"], "sub-slice-topology")

  @patch("xpk.core.kueue_manager.KueueManager._KueueManager__install")
  @patch(
      "xpk.core.kueue_manager.KueueManager._KueueManager__update_kueue_resources_if_necessary"
  )
  def test_configure_generates_correct_manifest_with_pathways(
      self, mock_update_resources, mock_install
  ):
    """Test that __configure generates the correct manifest with pathways enabled."""
    mock_install.return_value = 0
    mock_update_resources.return_value = 0
    kueue_config = KueueConfig(
        system=self.mock_system_chars,
        total_chips=8,
        cpu_limit=100,
        memory_limit="100Gi",
        is_pathways_cluster=True,
        num_slices=2,
        configure_sub_slicing=False,
    )

    rendered_manifest = self._trigger_installation(kueue_config)
    manifest_docs = list(yaml.safe_load_all(rendered_manifest))

    # Check for the new "cpu-user" ResourceFlavor
    cpu_user_flavor = _first(
        doc
        for doc in manifest_docs
        if doc["kind"] == "ResourceFlavor"
        and doc["metadata"]["name"] == "cpu-user"
    )
    self.assertEqual(
        cpu_user_flavor["spec"]["nodeLabels"]["cloud.google.com/gke-nodepool"],
        "cpu-np",
    )

    # Check that the ClusterQueue has the new resource group for pathways
    cluster_queue = _first(
        doc for doc in manifest_docs if doc["kind"] == "ClusterQueue"
    )
    self.assertEqual(len(cluster_queue["spec"]["resourceGroups"]), 2)
    pathways_rg = cluster_queue["spec"]["resourceGroups"][1]
    self.assertEqual(pathways_rg["coveredResources"], ["cpu", "memory"])
    self.assertEqual(pathways_rg["flavors"][0]["name"], "cpu-user")
    self.assertEqual(
        pathways_rg["flavors"][0]["resources"][0]["nominalQuota"], 480
    )
    self.assertEqual(
        pathways_rg["flavors"][0]["resources"][1]["nominalQuota"], "2000G"
    )

  def _trigger_installation(self, kueue_config: KueueConfig) -> str:
    """Calls Kueue installation and returns the rendered manifest."""
    with (
        patch.object(
            self.kueue_manager, "get_installed_kueue_version"
        ) as mock_get_version,
        patch.object(
            self.kueue_manager, "_KueueManager__apply_manifest"
        ) as mock_apply_manifest,
    ):
      mock_apply_manifest.return_value = 0
      mock_get_version.return_value = (1, None)
      self.kueue_manager.install_or_upgrade(kueue_config)

    mock_apply_manifest.assert_called_once()
    manifest = mock_apply_manifest.call_args[0][0]
    assert isinstance(manifest, str)
    return manifest


T = TypeVar("T")


def _first(generator: Generator[T, None, None]) -> T:
  result = next(generator, None)
  assert result is not None
  return result


if __name__ == "__main__":
  unittest.main()
