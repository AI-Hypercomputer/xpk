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

import unittest
from unittest.mock import MagicMock, patch

from xpk.core.kueue_manager import KueueConfig, KueueManager
from xpk.core.system_characteristics import AcceleratorType, SystemCharacteristics


class KueueManagerTest(unittest.TestCase):
  """Unit tests for the KueueManager class."""

  def setUp(self):
    """Set up test environment."""
    self.mock_system_chars = SystemCharacteristics(
        topology="2x2x1",
        vms_per_slice=1,
        gke_accelerator="test-accelerator",
        gce_machine_type="test-machine",
        chips_per_vm=4,
        accelerator_type=AcceleratorType["TPU"],
        device_type="v5p-8",
    )
    with patch("jinja2.Environment"):
      self.kueue_manager = KueueManager()

  def test_build_template_context_basic(self):
    """Test _build_template_context with a basic configuration."""
    context = self.kueue_manager._build_template_context(
        system=self.mock_system_chars,
        total_chips=8,
        is_pathways=False,
        autoprovisioning=False,
        flex=False,
        num_slices=2,
        cpu_limit=100,
        memory_limit="100Gi",
    )

    self.assertEqual(context["cluster_queue_name"], "cluster-queue")
    self.assertEqual(context["local_queue_name"], "multislice-queue")
    self.assertEqual(context["managed_resource"], "google.com/tpu")
    self.assertFalse(context["autoprovisioning_enabled"])
    self.assertEqual(context["admission_checks"], "")

    self.assertEqual(len(context["flavors"]), 1)
    self.assertEqual(context["flavors"][0]["name"], "2xv5p-8")
    self.assertEqual(
        context["flavors"][0]["nodeLabels"],
        {
            "cloud.google.com/gke-tpu-accelerator": "test-accelerator",
            "cloud.google.com/gke-tpu-topology": "2x2x1",
        },
    )

    self.assertEqual(len(context["resource_groups"]), 1)
    self.assertIn(
        "google.com/tpu", context["resource_groups"][0]["coveredResources"]
    )
    self.assertIn("cpu", context["resource_groups"][0]["coveredResources"])
    self.assertIn("memory", context["resource_groups"][0]["coveredResources"])

    resources = context["resource_groups"][0]["flavors"][0]["resources"]
    self.assertIn({"name": "google.com/tpu", "nominalQuota": 8}, resources)
    self.assertIn({"name": "cpu", "nominalQuota": 100}, resources)
    self.assertIn({"name": "memory", "nominalQuota": "100Gi"}, resources)

  def test_build_template_context_with_pathways(self):
    """Test _build_template_context with Pathways enabled."""
    context = self.kueue_manager._build_template_context(
        system=self.mock_system_chars,
        total_chips=8,
        is_pathways=True,
        autoprovisioning=False,
        flex=False,
        num_slices=2,
        cpu_limit=100,
        memory_limit="100Gi",
    )

    self.assertEqual(len(context["flavors"]), 2)
    self.assertEqual(context["flavors"][1]["name"], "cpu-user")
    self.assertEqual(
        context["flavors"][1]["nodeLabels"],
        {"cloud.google.com/gke-nodepool": "cpu-np"},
    )

    self.assertEqual(len(context["resource_groups"]), 2)
    self.assertEqual(
        context["resource_groups"][1]["coveredResources"], ["cpu", "memory"]
    )

  def test_build_template_context_with_flex(self):
    """Test _build_template_context with flex enabled."""
    context = self.kueue_manager._build_template_context(
        system=self.mock_system_chars,
        total_chips=8,
        is_pathways=False,
        autoprovisioning=False,
        flex=True,
        num_slices=2,
        cpu_limit=100,
        memory_limit="100Gi",
    )
    self.assertIn("admissionChecks", context["admission_checks"])
    self.assertIn("dws-prov", context["admission_checks"])

  @patch("xpk.core.kueue_manager.run_command_for_value")
  def test_get_installed_kueue_version(self, mock_run_command):
    """Test _get_installed_kueue_version."""
    mock_run_command.return_value = (
        0,
        "Client Version:v0.12.1\nManager Version:v0.12.2",
    )
    ret_code, version = self.kueue_manager._get_installed_kueue_version()
    self.assertEqual(ret_code, 0)
    self.assertEqual(version, "v0.12.2")

  @patch("xpk.core.kueue_manager.KueueManager._get_installed_kueue_version")
  @patch("xpk.core.kueue_manager.KueueManager._install")
  @patch("xpk.core.kueue_manager.KueueManager._configure")
  def test_install_or_upgrade_when_up_to_date(
      self, mock_configure, mock_install, mock_get_version
  ):
    """Test install_or_upgrade when Kueue is already up to date."""
    mock_get_version.return_value = (0, "v0.12.2")
    kueue_config = MagicMock(spec=KueueConfig)

    result = self.kueue_manager.install_or_upgrade(kueue_config)

    self.assertEqual(result, 0)
    mock_get_version.assert_called_once()
    mock_install.assert_not_called()
    mock_configure.assert_not_called()

  @patch("xpk.core.kueue_manager.KueueManager._get_installed_kueue_version")
  @patch("xpk.core.kueue_manager.KueueManager._install")
  @patch("xpk.core.kueue_manager.KueueManager._configure")
  def test_install_or_upgrade_when_outdated(
      self, mock_configure, mock_install, mock_get_version
  ):
    """Test install_or_upgrade when an older version of Kueue is installed."""
    mock_get_version.return_value = (0, "v0.11.0")
    mock_install.return_value = 0
    mock_configure.return_value = 0
    kueue_config = MagicMock(spec=KueueConfig)

    result = self.kueue_manager.install_or_upgrade(kueue_config)

    self.assertEqual(result, 0)
    mock_get_version.assert_called_once()
    mock_install.assert_called_once()
    mock_configure.assert_called_once()

  @patch("xpk.core.kueue_manager.KueueManager._get_installed_kueue_version")
  @patch("xpk.core.kueue_manager.KueueManager._install")
  @patch("xpk.core.kueue_manager.KueueManager._configure")
  def test_install_or_upgrade_when_not_installed(
      self, mock_configure, mock_install, mock_get_version
  ):
    """Test install_or_upgrade when Kueue is not installed."""
    mock_get_version.return_value = (1, "")
    mock_install.return_value = 0
    mock_configure.return_value = 0
    kueue_config = MagicMock(spec=KueueConfig)

    result = self.kueue_manager.install_or_upgrade(kueue_config)

    self.assertEqual(result, 0)
    mock_get_version.assert_called_once()
    mock_install.assert_called_once()
    mock_configure.assert_called_once()

  @patch("xpk.core.kueue_manager.run_command_with_updates_retry")
  @patch("xpk.core.kueue_manager.KueueManager._wait_for_kueue_available")
  def test_install_with_tolerations(self, mock_wait, mock_run_retry):
    """Test the _install method with tolerations."""
    mock_run_retry.return_value = 0
    mock_wait.return_value = 0
    tolerations = [
        {"key": "test", "operator": "Exists", "effect": "NoSchedule"}
    ]

    result = self.kueue_manager._install(tolerations=tolerations)

    self.assertEqual(result, 0)
    self.assertEqual(mock_run_retry.call_count, 2)
    install_call = mock_run_retry.call_args_list[0]
    self.assertIn("kubectl apply", install_call[0][0])
    patch_call = mock_run_retry.call_args_list[1]
    self.assertIn("kubectl patch", patch_call[0][0])
    self.assertIn('"tolerations":', patch_call[0][0])
    mock_wait.assert_called_once()

  @patch("xpk.core.kueue_manager.run_command_with_updates_retry")
  @patch("xpk.core.kueue_manager.KueueManager._wait_for_kueue_available")
  def test_install_without_tolerations(self, mock_wait, mock_run_retry):
    """Test the _install method without tolerations."""
    mock_run_retry.return_value = 0
    mock_wait.return_value = 0

    result = self.kueue_manager._install(tolerations=None)

    self.assertEqual(result, 0)
    mock_run_retry.assert_called_once()
    install_call = mock_run_retry.call_args_list[0]
    self.assertIn("kubectl apply", install_call[0][0])
    mock_wait.assert_called_once()

  @patch("xpk.core.kueue_manager.KueueManager._apply_manifest")
  @patch(
      "xpk.core.kueue_manager.KueueManager._update_kueue_resources_if_necessary"
  )
  def test_configure(self, mock_update_resources, mock_apply_manifest):
    """Test the _configure method."""
    mock_apply_manifest.return_value = 0
    mock_update_resources.return_value = 0
    self.kueue_manager.template_env.get_template = MagicMock()
    mock_template = self.kueue_manager.template_env.get_template.return_value
    mock_template.render.return_value = "---"

    kueue_config = KueueConfig(
        system=self.mock_system_chars,
        total_chips=8,
        cpu_limit=100,
        memory_limit="100Gi",
    )

    result = self.kueue_manager._configure(kueue_config)

    self.assertEqual(result, 0)
    mock_apply_manifest.assert_called_once_with("---")
    mock_update_resources.assert_called_once()

  @patch("xpk.core.kueue_manager.run_command_for_value")
  @patch("xpk.core.kueue_manager.run_command_with_updates_retry")
  def test_update_kueue_resources_if_necessary(
      self, mock_run_retry, mock_run_for_value
  ):
    """Test _update_kueue_resources_if_necessary."""
    mock_run_for_value.return_value = (0, "100")  # 100 nodes
    mock_run_retry.return_value = 0

    result = self.kueue_manager._update_kueue_resources_if_necessary()

    self.assertEqual(result, 0)
    mock_run_for_value.assert_called_once()
    mock_run_retry.assert_called_once()
    patch_call = mock_run_retry.call_args_list[0]
    self.assertIn("kubectl patch", patch_call[0][0])
    # 100 * 1.2 = 120, which is less than 4096. So it should be 4096.
    self.assertIn('"memory": "4096Mi"', patch_call[0][0])

  @patch("xpk.core.kueue_manager.run_command_for_value")
  @patch("xpk.core.kueue_manager.run_command_with_updates_retry")
  def test_update_kueue_resources_if_necessary_large_cluster(
      self, mock_run_retry, mock_run_for_value
  ):
    """Test _update_kueue_resources_if_necessary for a large cluster."""
    mock_run_for_value.return_value = (0, "5000")  # 5000 nodes
    mock_run_retry.return_value = 0

    result = self.kueue_manager._update_kueue_resources_if_necessary()

    self.assertEqual(result, 0)
    mock_run_for_value.assert_called_once()
    mock_run_retry.assert_called_once()
    patch_call = mock_run_retry.call_args_list[0]
    self.assertIn("kubectl patch", patch_call[0][0])
    # 5000 * 1.2 = 6000, which is > 4096.
    self.assertIn('"memory": "6000Mi"', patch_call[0][0])


if __name__ == "__main__":
  unittest.main()
