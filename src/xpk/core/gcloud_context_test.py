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
from .gcloud_context import (
    get_cluster_location,
    get_gke_control_plane_version,
    get_gke_server_config,
    GkeServerConfig,
    zone_to_region,
)
from ..utils.versions import ReleaseChannel


@pytest.fixture(autouse=True)
def xpk_print(mocker):
  return mocker.patch("xpk.core.gcloud_context.xpk_print")


def test_zone_to_region_raises_when_zone_is_invalid():
  with pytest.raises(ValueError):
    zone_to_region("us")


def test_zone_to_region_returns_region_when_region_given():
  assert zone_to_region("us-central1") == "us-central1"


def test_zone_to_region_returns_region_when_zone_is_valid():
  assert zone_to_region("us-central1-a") == "us-central1"


def test_get_cluster_location_returns_cluster_region_when_cluster_is_regional(
    mocker,
):
  mocker.patch(
      "xpk.core.gcloud_context.run_command_for_value",
      return_value=(0, "us-central1"),
  )

  result = get_cluster_location(
      project="project1", name="name1", zone="us-central1-a"
  )

  assert result == "us-central1"


def test_get_cluster_location_returns_cluster_zone_when_both_regional_and_zonal_clusters_exist(
    mocker,
):
  mocker.patch(
      "xpk.core.gcloud_context.run_command_for_value",
      return_value=(0, "us-central1\nus-central1-a"),
  )

  result = get_cluster_location(
      project="project2", name="name2", zone="us-central1-a"
  )

  assert result == "us-central1-a"


def test_get_cluster_location_returns_given_zone_converted_to_region_when_cluster_is_not_found(
    mocker,
):
  mocker.patch(
      "xpk.core.gcloud_context.run_command_for_value", return_value=(0, "")
  )

  result = get_cluster_location(
      project="project3", name="name3", zone="us-central1-a"
  )

  assert result == "us-central1"


def test_get_cluster_location_caches_previous_command_result(mocker):
  mock = mocker.patch(
      "xpk.core.gcloud_context.run_command_for_value", return_value=(0, "")
  )

  get_cluster_location(project="project4", name="name4", zone="us-central1-a")

  assert mock.call_count == 1


def test_get_cluster_location_invokes_command_for_different_input_args(mocker):
  mock = mocker.patch(
      "xpk.core.gcloud_context.run_command_for_value", return_value=(0, "")
  )

  get_cluster_location(project="project5", name="name5", zone="us-central1-a")
  get_cluster_location(project="project6", name="name6", zone="us-central1-a")

  assert mock.call_count == 2


def test_get_gke_server_config_success(mocker):
  mock_run_command = mocker.patch(
      "xpk.core.gcloud_context.run_command_for_value",
      side_effect=[
          (0, "1.2.3"),
          (0, "1.2.3;1.2.4;1.3.0"),
      ],
  )
  args = mocker.Mock(project="test-project", zone="us-central1")

  return_code, config = get_gke_server_config(args, ReleaseChannel.STABLE)

  assert return_code == 0
  assert isinstance(config, GkeServerConfig)
  assert config.default_gke_version == "1.2.3"
  assert config.valid_versions == {"1.2.3", "1.2.4", "1.3.0"}
  assert mock_run_command.call_count == 2


def test_get_gke_server_config_fails_on_default_version_command(mocker):
  mocker.patch(
      "xpk.core.gcloud_context.run_command_for_value",
      return_value=(1, "error"),
  )
  args = mocker.Mock(project="test-project", zone="us-central1")

  return_code, config = get_gke_server_config(args, ReleaseChannel.STABLE)

  assert return_code == 1
  assert config is None


def test_get_gke_server_config_fails_on_valid_versions_command(mocker):
  mocker.patch(
      "xpk.core.gcloud_context.run_command_for_value",
      side_effect=[(0, "1.2.3"), (1, "error")],
  )
  args = mocker.Mock(project="test-project", zone="us-central1")

  return_code, config = get_gke_server_config(args, ReleaseChannel.STABLE)

  assert return_code == 1
  assert config is None


def test_get_gke_control_plane_version_uses_default_when_not_specified(mocker):
  args = mocker.Mock(gke_version=None)
  gke_server_config = GkeServerConfig(
      default_gke_version="1.2.3", valid_versions={"1.2.3", "1.2.4"}
  )

  return_code, version = get_gke_control_plane_version(args, gke_server_config)

  assert return_code == 0
  assert version == "1.2.3"


def test_get_gke_control_plane_version_uses_user_version_when_valid(mocker):
  args = mocker.Mock(gke_version="1.2.4")
  gke_server_config = GkeServerConfig(
      default_gke_version="1.2.3", valid_versions={"1.2.3", "1.2.4"}
  )

  return_code, version = get_gke_control_plane_version(args, gke_server_config)

  assert return_code == 0
  assert version == "1.2.4"


def test_get_gke_control_plane_version_fails_for_invalid_user_version(
    mocker, xpk_print: MagicMock
):
  args = mocker.Mock(gke_version="1.2.5")
  gke_server_config = GkeServerConfig(
      default_gke_version="1.2.3", valid_versions={"1.2.3", "1.2.4"}
  )

  return_code, version = get_gke_control_plane_version(args, gke_server_config)

  assert return_code == 1
  assert version is None
  assert "Planned GKE Version: 1.2.5" in xpk_print.mock_calls[0].args[0]
  assert (
      "Recommended / Default GKE Version: 1.2.3"
      in xpk_print.mock_calls[0].args[0]
  )
  assert (
      "Error: Planned GKE Version 1.2.5 is not valid."
      in xpk_print.mock_calls[1].args[0]
  )
  assert (
      "Please select a gke version from the above list using --gke-version=x"
      " argument or rely on the default gke version: 1.2.3"
      in xpk_print.mock_calls[2].args[0]
  )
