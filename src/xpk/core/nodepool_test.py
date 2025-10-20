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
from xpk.core.nodepool import (
    ensure_resource_policy_exists,
    get_desired_node_pool_names,
    run_gke_node_pool_create_command,
)
from xpk.core.system_characteristics import AcceleratorType, SystemCharacteristics

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
  mocker.patch("xpk.core.nodepool.get_cluster_location", return_value=args.zone)
  mock = mocker.patch(
      "xpk.core.nodepool.run_command_for_value", return_value=(0, "")
  )
  ensure_resource_policy_exists("resource-policy", args, "2x2x1")
  mock.assert_called_once()


def test_ensure_resource_policy_exists_without_existing_policy_creates_policy(
    mocker,
):
  args = mocker.Mock(project="test-project", zone="us-central1-a")
  mocker.patch("xpk.core.nodepool.get_cluster_location", return_value=args.zone)
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
        "xpk.core.nodepool.get_cluster_location", return_value=args.zone
    )
    mocker.patch(
        "xpk.core.nodepool.run_command_for_value",
        side_effect=[(1, ""), (1, "")],
    )
    ensure_resource_policy_exists("resource-policy", args, "2x2x1")


@pytest.fixture
def mock_nodepool_dependencies(mocker):
  """Mocks dependencies for run_gke_node_pool_create_command."""
  mocker.patch(
      "xpk.core.nodepool.get_all_nodepools_programmatic", return_value=([], 0)
  )
  mocker.patch(
      "xpk.core.nodepool.get_capacity_type", return_value=("on-demand", 0)
  )
  mocker.patch(
      "xpk.core.nodepool.get_capacity_arguments_from_capacity_type",
      return_value=("--on-demand", 0),
  )
  mocker.patch(
      "xpk.core.nodepool.get_cluster_location", return_value="us-central1"
  )
  mocker.patch("xpk.core.nodepool.run_commands", return_value=0)
  mocker.patch("xpk.core.nodepool.get_user_input", return_value=True)
  mock_is_topology_valid = mocker.patch("xpk.core.nodepool.is_topology_valid")
  mock_ensure_resource_policy = mocker.patch(
      "xpk.core.nodepool.ensure_resource_policy_exists"
  )
  return mock_is_topology_valid, mock_ensure_resource_policy


def test_placement_policy_created_for_gpu_with_valid_topology(
    mocker, mock_nodepool_dependencies
):
  """Tests that placement policy is created for GPUs with a valid topology."""
  mock_is_topology_valid, mock_ensure_resource_policy = (
      mock_nodepool_dependencies
  )
  mock_is_topology_valid.return_value = True
  args = mocker.Mock(
      tpu_type=None,
      device_type="h100-80gb-8",
      cluster="test-cluster",
      project="test-project",
      zone="us-central1-a",
  )
  system = SystemCharacteristics(
      topology="N/A",
      vms_per_slice=1,
      gke_accelerator="nvidia-h100-80gb",
      gce_machine_type="a3-highgpu-8g",
      chips_per_vm=8,
      accelerator_type=AcceleratorType["GPU"],
      device_type="h100-80gb-8",
      supports_sub_slicing=False,
  )

  run_gke_node_pool_create_command(args, system, "1.2.3")

  mock_ensure_resource_policy.assert_called_once()


def test_placement_policy_not_created_for_gpu_with_invalid_topology(
    mocker, mock_nodepool_dependencies
):
  """Tests that placement policy is not created for GPUs with an invalid topology."""
  mock_is_topology_valid, mock_ensure_resource_policy = (
      mock_nodepool_dependencies
  )
  mock_is_topology_valid.return_value = False
  args = mocker.Mock(
      tpu_type=None,
      device_type="h100-80gb-8",
      cluster="test-cluster",
      zone="us-central1-a",
  )
  system = SystemCharacteristics(
      topology="N/A",
      vms_per_slice=1,
      gke_accelerator="nvidia-h100-80gb",
      gce_machine_type="a3-highgpu-8g",
      chips_per_vm=8,
      accelerator_type=AcceleratorType["GPU"],
      device_type="h100-80gb-8",
      supports_sub_slicing=False,
  )

  run_gke_node_pool_create_command(args, system, "1.2.3")

  mock_ensure_resource_policy.assert_not_called()


def test_placement_policy_created_for_tpu7x_with_valid_topology(
    mocker, mock_nodepool_dependencies
):
  """Tests that placement policy is created for tpu7x with a valid topology."""
  mock_is_topology_valid, mock_ensure_resource_policy = (
      mock_nodepool_dependencies
  )
  mock_is_topology_valid.return_value = True
  args = mocker.Mock(
      tpu_type="tpu7x-8",
      device_type=None,
      num_slices=1,
      cluster="test-cluster",
      project="test-project",
      zone="us-central1-a",
  )
  system = SystemCharacteristics(
      topology="2x2x1",
      vms_per_slice=1,
      gke_accelerator="tpu7x",
      gce_machine_type="tpu7x-standard-4t",
      chips_per_vm=4,
      accelerator_type=AcceleratorType["TPU"],
      device_type="tpu7x-8",
      requires_workload_policy=True,
      supports_sub_slicing=False,
  )

  run_gke_node_pool_create_command(args, system, "1.2.3")

  mock_ensure_resource_policy.assert_called_once()


def test_placement_policy_not_created_for_non7x_tpu(
    mocker, mock_nodepool_dependencies
):
  """Tests that placement policy is not created for non-tpu7x TPUs."""
  mock_is_topology_valid, mock_ensure_resource_policy = (
      mock_nodepool_dependencies
  )
  mock_is_topology_valid.return_value = True
  args = mocker.Mock(
      tpu_type="v6e",
      device_type=None,
      num_slices=1,
      cluster="test-cluster",
      project="test-project",
      zone="us-central1-a",
  )
  system = SystemCharacteristics(
      topology="2x2",
      vms_per_slice=1,
      gke_accelerator="v6e",
      gce_machine_type="tpu-v6e-slice",
      chips_per_vm=4,
      accelerator_type=AcceleratorType["TPU"],
      device_type="v6e-4",
      supports_sub_slicing=True,
  )

  run_gke_node_pool_create_command(args, system, "1.2.3")

  mock_ensure_resource_policy.assert_not_called()
