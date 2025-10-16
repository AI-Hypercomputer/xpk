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
from .gcloud_context import get_cluster_location, zone_to_region


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
