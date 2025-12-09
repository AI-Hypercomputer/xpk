"""
Copyright 2024 Google LLC

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

from unittest.mock import MagicMock, patch

import pytest

from xpk.commands.cluster_gcluster import cluster_create
from xpk.core.kueue_manager import KueueConfig
from xpk.core.system_characteristics import AcceleratorType, SystemCharacteristics, DockerPlatform, GpuConfig
from xpk.utils.versions import ReleaseChannel


@pytest.fixture
def mock_args():
  """Provides a mock for args."""
  args = MagicMock()
  args.enable_autoprovisioning = False
  args.num_slices = 1
  args.memory_limit = "200G"
  args.cpu_limit = "50"
  args.enable_pathways = False
  args.flex = False
  args.project = "test-project"
  args.cluster = "test-cluster"
  args.zone = "us-central1-c"
  args.cluster_state_gcs_bucket = None
  return args


@pytest.fixture
def mock_cluster_create_deps(request):
  """Mocks dependencies for cluster_create."""
  with (
      patch("xpk.commands.cluster_gcluster.xpk_exit") as mock_exit,
      patch(
          "xpk.commands.cluster_gcluster.get_cluster_credentials"
      ) as mock_get_creds,
      patch("xpk.commands.cluster_gcluster.generate_blueprint") as mock_gen_bp,
      patch(
          "xpk.commands.cluster_gcluster.prepare_gcluster_manager"
      ) as mock_prep_gcm,
      patch(
          "xpk.commands.cluster_gcluster.prepare_directories"
      ) as mock_prep_dirs,
      patch(
          "xpk.commands.cluster_gcluster.check_gcloud_authenticated"
      ) as mock_check_auth,
      patch(
          "xpk.commands.cluster_gcluster.get_system_characteristics"
      ) as mock_get_sys_char,
      patch("xpk.commands.cluster_gcluster.KueueManager") as mock_kueue_manager,
  ):
    yield {
        "xpk_exit": mock_exit,
        "get_cluster_credentials": mock_get_creds,
        "generate_blueprint": mock_gen_bp,
        "prepare_gcluster_manager": mock_prep_gcm,
        "prepare_directories": mock_prep_dirs,
        "check_gcloud_authenticated": mock_check_auth,
        "get_system_characteristics": mock_get_sys_char,
        "KueueManager": mock_kueue_manager,
    }


@patch("xpk.commands.cluster_gcluster.get_total_chips_requested_from_args")
def test_install_kueue_standard(
    mock_get_total_chips, mock_args, mock_cluster_create_deps
):
  """Tests __install_kueue for a standard installation."""
  mock_system = SystemCharacteristics(
      topology="N/A",
      vms_per_slice=1,
      gke_accelerator="nvidia-h100-mega-80gb",
      gce_machine_type="a3-megagpu-8g",
      chips_per_vm=8,
      accelerator_type=AcceleratorType.GPU,
      device_type="h100-mega-80gb-8",
      supports_sub_slicing=False,
      supports_super_slicing=False,
      docker_platform=DockerPlatform.ARM,
      gpu_config=GpuConfig(requires_topology=True),
  )
  mock_cluster_create_deps["get_system_characteristics"].return_value = (
      mock_system,
      0,
  )
  mock_get_total_chips.return_value = 16

  cluster_create(
      mock_args,
      release_channel=ReleaseChannel.RAPID,
      gke_control_plane_version="1.2.3",
  )

  mock_cluster_create_deps["xpk_exit"].assert_called_with(0)
  mock_kueue_manager = mock_cluster_create_deps["KueueManager"]
  mock_kueue_manager.return_value.install_or_upgrade.assert_called_once()
  call_args, call_kwargs = (
      mock_kueue_manager.return_value.install_or_upgrade.call_args
  )
  kueue_config: KueueConfig = call_args[0]

  assert kueue_config.system == mock_system
  assert kueue_config.total_chips == 16
  assert not kueue_config.autoprovisioning_enabled
  assert "tolerations" in call_kwargs
  tolerations = call_kwargs["tolerations"]
  assert any(
      t.get("key") == "components.gke.io/gke-managed-components"
      and t.get("effect") == "NoSchedule"
      for t in tolerations
  )


@patch("xpk.commands.cluster_gcluster.enable_autoprovisioning_on_cluster")
def test_install_kueue_with_autoprovisioning(
    mock_enable_autoprovisioning, mock_args, mock_cluster_create_deps
):
  """Tests __install_kueue with autoprovisioning enabled."""
  mock_args.enable_autoprovisioning = True
  mock_system = SystemCharacteristics(
      topology="N/A",
      vms_per_slice=1,
      gke_accelerator="nvidia-h100-mega-80gb",
      gce_machine_type="a3-megagpu-8g",
      chips_per_vm=8,
      accelerator_type=AcceleratorType.GPU,
      device_type="h100-mega-80gb-8",
      supports_sub_slicing=False,
      supports_super_slicing=False,
      docker_platform=DockerPlatform.ARM,
      gpu_config=GpuConfig(requires_topology=True),
  )
  mock_cluster_create_deps["get_system_characteristics"].return_value = (
      mock_system,
      0,
  )

  mock_autoprovisioning_config = MagicMock()
  mock_autoprovisioning_config.maximum_chips = 128
  mock_enable_autoprovisioning.return_value = (mock_autoprovisioning_config, 0)

  cluster_create(
      mock_args,
      release_channel=ReleaseChannel.RAPID,
      gke_control_plane_version="1.2.3",
  )

  mock_cluster_create_deps["xpk_exit"].assert_called_with(0)
  mock_enable_autoprovisioning.assert_called_once_with(mock_args, mock_system)
  mock_kueue_manager = mock_cluster_create_deps["KueueManager"]
  mock_kueue_manager.return_value.install_or_upgrade.assert_called_once()

  call_args, call_kwargs = (
      mock_kueue_manager.return_value.install_or_upgrade.call_args
  )
  kueue_config: KueueConfig = call_args[0]

  assert kueue_config.system == mock_system
  assert kueue_config.total_chips == 128
  assert kueue_config.autoprovisioning_enabled
  assert "tolerations" in call_kwargs
  tolerations = call_kwargs["tolerations"]
  assert any(
      t.get("key") == "components.gke.io/gke-managed-components"
      and t.get("effect") == "NoSchedule"
      for t in tolerations
  )
