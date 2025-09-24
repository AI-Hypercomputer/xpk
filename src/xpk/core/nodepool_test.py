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
from xpk.core.nodepool import get_desired_node_pool_names, ensure_resource_policy_exists

CLUSTER_NAME = "running-cucumber"


def node_pool_name(number: int) -> str:
  return f"{CLUSTER_NAME}-np-{number}"


def test_compute_desired_node_pool_names_with_desired_larger_than_existing():
  result = get_desired_node_pool_names(
      existing_node_pool_names=[node_pool_name(0)],
      cluster_name=CLUSTER_NAME,
      desired_node_pool_count=2,
  )

  expected_result = [node_pool_name(0), node_pool_name(1)]
  assert set(result) == set(expected_result)


def test_compute_desired_node_pool_names_with_desired_smaller_than_existing():
  result = get_desired_node_pool_names(
      existing_node_pool_names=[node_pool_name(0), node_pool_name(1)],
      cluster_name=CLUSTER_NAME,
      desired_node_pool_count=1,
  )

  expected_result = [node_pool_name(0)]
  assert set(result) == set(expected_result)


def test_compute_desired_node_pool_names_with_consecutive_numbers_missing():
  result = get_desired_node_pool_names(
      existing_node_pool_names=[node_pool_name(0), node_pool_name(3)],
      cluster_name=CLUSTER_NAME,
      desired_node_pool_count=3,
  )

  expected_result = [node_pool_name(0), node_pool_name(1), node_pool_name(3)]
  assert set(result) == set(expected_result)


def test_compute_desired_node_pool_names_with_consecutive_numbers_missing_and_desired_equal_to_existing():
  result = get_desired_node_pool_names(
      existing_node_pool_names=[node_pool_name(0), node_pool_name(3)],
      cluster_name=CLUSTER_NAME,
      desired_node_pool_count=2,
  )

  expected_result = [node_pool_name(0), node_pool_name(3)]
  assert set(result) == set(expected_result)


def test_compute_desired_node_pool_names_with_unknown_node_pools():
  result = get_desired_node_pool_names(
      existing_node_pool_names=[
          "unknown-node-pool",
          node_pool_name(0),
          node_pool_name(3),
      ],
      cluster_name=CLUSTER_NAME,
      desired_node_pool_count=2,
  )

  expected_result = [node_pool_name(0), node_pool_name(3)]
  assert set(result) == set(expected_result)


def test_ensure_resource_policy_exists_with_existing_policy_retrieves_existing_policy(
    mocker,
):
  args = mocker.Mock(project="test-project", zone="us-central1-a")
  mock = mocker.patch(
      "xpk.core.nodepool.run_command_for_value", return_value=(0, "")
  )
  ensure_resource_policy_exists("resource-policy", args, "2x2x1")
  mock.assert_called_once()


def test_ensure_resource_policy_exists_without_existing_policy_creates_policy(
    mocker,
):
  args = mocker.Mock(project="test-project", zone="us-central1-a")
  mock = mocker.patch(
      "xpk.core.nodepool.run_command_for_value", side_effect=[(1, ""), (0, "")]
  )
  ensure_resource_policy_exists("resource-policy", args, "2x2x1")
  assert mock.call_count == 2
  assert mock.call_args_list[0].args[1] == "Retrieve resource policy"


def test_ensure_resource_policy_exits_without_existing_policy_throws_when_creation_fails(
    mocker,
):
  with pytest.raises(RuntimeError):
    args = mocker.Mock(project="test-project", zone="us-central1-a")
    mocker.patch(
        "xpk.core.nodepool.run_command_for_value",
        side_effect=[(1, ""), (1, "")],
    )
    ensure_resource_policy_exists("resource-policy", args, "2x2x1")
