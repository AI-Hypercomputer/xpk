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
    display_nodepool_creation_error,
    ensure_resource_policy_exists,
    get_desired_node_pool_names,
    run_gke_node_pool_create_command,
)
from xpk.core.system_characteristics import AcceleratorType, SystemCharacteristics, DockerPlatform, GpuConfig
from xpk.core.commands import FailedCommand
from xpk.core.testing.commands_tester import CommandsTester


CLUSTER_NAME = "running-cucumber"
maybe_failure = FailedCommand(
    return_code=1,
    name="create-nodepool",
    command="test-command",
    logfile="logfile_path",
)


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


@pytest.fixture
def commands_tester(mocker):
  return CommandsTester(
      mocker,
      run_command_for_value_path="xpk.core.nodepool.run_command_for_value",
  )


def test_ensure_resource_policy_exists_with_existing_policy_retrieves_existing_policy(
    commands_tester: CommandsTester,
):
  ensure_resource_policy_exists(
      resource_policy_name="resource-policy",
      project="test-project",
      zone="us-central1-a",
      topology="2x2x1",
      super_slicing=False,
  )

  assert len(commands_tester.commands_history) == 1
  commands_tester.assert_command_run(
      "gcloud compute resource-policies describe resource-policy",
      "--project=test-project",
      "--region=us-central1",
  )


def test_ensure_resource_policy_exists_without_existing_policy_creates_policy(
    commands_tester: CommandsTester,
):
  commands_tester.set_result_for_command(
      (1, ""), "gcloud compute resource-policies describe"
  )

  ensure_resource_policy_exists(
      resource_policy_name="resource-policy",
      project="test-project",
      zone="us-central1-a",
      topology="2x2x1",
      super_slicing=False,
  )

  assert len(commands_tester.commands_history) == 2
  commands_tester.assert_command_run(
      "gcloud compute resource-policies describe"
  )
  commands_tester.assert_command_run(
      "gcloud compute resource-policies create workload-policy resource-policy",
      "--project=test-project",
      "--region=us-central1",
      "--accelerator-topology=2x2x1",
  )
  commands_tester.assert_command_not_run(
      "gcloud compute resource-policies create workload-policy",
      "--accelerator-topology-mode",
  )


def test_ensure_resource_policy_exists_without_existing_policy_creates_policy_for_super_slicing(
    commands_tester: CommandsTester,
):
  commands_tester.set_result_for_command(
      (1, ""), "gcloud compute resource-policies describe"
  )

  ensure_resource_policy_exists(
      resource_policy_name="ss-resource-policy",
      project="test-project",
      zone="us-central1-a",
      topology="2x2x1",
      super_slicing=True,
  )

  commands_tester.assert_command_run(
      "gcloud compute resource-policies create workload-policy",
      "--accelerator-topology-mode",
  )


def test_ensure_resource_policy_exits_without_existing_policy_throws_when_creation_fails(
    commands_tester: CommandsTester,
):
  with pytest.raises(RuntimeError):
    commands_tester.set_result_for_command(
        (1, ""), "gcloud compute resource-policies"
    )

    ensure_resource_policy_exists(
        resource_policy_name="resource-policy",
        project="test-project",
        zone="us-central1-a",
        topology="2x2x1",
        super_slicing=False,
    )


@pytest.fixture
def mock_xpk_print(mocker):
  return mocker.patch("xpk.core.nodepool.xpk_print")


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
  mocker.patch("xpk.core.nodepool.run_commands", return_value=None)
  mocker.patch("xpk.core.nodepool.ask_for_user_consent", return_value=True)
  mock_is_placement_policy_supported = mocker.patch(
      "xpk.core.nodepool.is_placement_policy_supported"
  )
  mock_ensure_resource_policy = mocker.patch(
      "xpk.core.nodepool.ensure_resource_policy_exists"
  )
  return mock_is_placement_policy_supported, mock_ensure_resource_policy


def test_placement_policy_created_for_gpu_with_valid_topology(
    mocker, mock_nodepool_dependencies
):
  """Tests that placement policy is created for GPUs with a valid topology."""
  mock_is_placement_policy_supported, mock_ensure_resource_policy = (
      mock_nodepool_dependencies
  )
  mock_is_placement_policy_supported.return_value = True
  args = mocker.Mock(
      tpu_type=None,
      device_type="h100-80gb-8",
      cluster="test-cluster",
      project="test-project",
      zone="us-central1-a",
  )
  system = SystemCharacteristics(
      topology="N/A",
      vms_per_slice=2,
      gke_accelerator="nvidia-h100-80gb",
      gce_machine_type="a3-highgpu-8g",
      chips_per_vm=8,
      accelerator_type=AcceleratorType.GPU,
      device_type="h100-80gb-8",
      supports_sub_slicing=False,
      supports_super_slicing=False,
      docker_platform=DockerPlatform.ARM,
      gpu_config=GpuConfig(requires_topology=True),
  )

  run_gke_node_pool_create_command(args, system, "1.2.3")

  mock_ensure_resource_policy.assert_called_once()


def test_placement_policy_not_created_for_gpu_with_invalid_topology(
    mocker, mock_nodepool_dependencies
):
  """Tests that placement policy is not created for GPUs with an invalid topology."""
  mock_is_placement_policy_supported, mock_ensure_resource_policy = (
      mock_nodepool_dependencies
  )
  mock_is_placement_policy_supported.return_value = False
  args = mocker.Mock(
      tpu_type=None,
      device_type="h100-80gb-8",
      cluster="test-cluster",
      zone="us-central1-a",
  )
  system = SystemCharacteristics(
      topology="N/A",
      vms_per_slice=2,
      gke_accelerator="nvidia-h100-80gb",
      gce_machine_type="a3-highgpu-8g",
      chips_per_vm=8,
      accelerator_type=AcceleratorType.GPU,
      device_type="h100-80gb-8",
      supports_sub_slicing=False,
      supports_super_slicing=False,
      docker_platform=DockerPlatform.ARM,
      gpu_config=GpuConfig(requires_topology=True),
  )

  run_gke_node_pool_create_command(args, system, "1.2.3")

  mock_ensure_resource_policy.assert_not_called()


def test_placement_policy_created_for_tpu7x_with_valid_topology(
    mocker, mock_nodepool_dependencies
):
  """Tests that placement policy is created for tpu7x with a valid topology."""
  mock_is_placement_policy_supported, mock_ensure_resource_policy = (
      mock_nodepool_dependencies
  )
  mock_is_placement_policy_supported.return_value = True
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
      vms_per_slice=2,
      gke_accelerator="tpu7x",
      gce_machine_type="tpu7x-standard-4t",
      chips_per_vm=4,
      accelerator_type=AcceleratorType.TPU,
      device_type="tpu7x-8",
      requires_workload_policy=True,
      supports_sub_slicing=False,
      supports_super_slicing=False,
      docker_platform=DockerPlatform.ARM,
  )

  run_gke_node_pool_create_command(args, system, "1.2.3")

  mock_ensure_resource_policy.assert_called_once()


def test_placement_policy_not_created_for_non7x_tpu(
    mocker, mock_nodepool_dependencies
):
  """Tests that placement policy is not created for non-tpu7x TPUs."""
  mock_is_placement_policy_supported, mock_ensure_resource_policy = (
      mock_nodepool_dependencies
  )
  mock_is_placement_policy_supported.return_value = False
  args = mocker.Mock(
      tpu_type="v6e",
      device_type=None,
      num_slices=2,
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
      accelerator_type=AcceleratorType.TPU,
      device_type="v6e-4",
      supports_sub_slicing=True,
      supports_super_slicing=False,
      docker_platform=DockerPlatform.ARM,
  )

  run_gke_node_pool_create_command(args, system, "1.2.3")

  mock_ensure_resource_policy.assert_not_called()


@pytest.mark.parametrize(
    argnames="error_message,is_stockout",
    argvalues=[
        (
            (
                "Requested resource is exhausted: Zone 'us-central1-c' is not"
                " available. Please try another zone."
            ),
            True,
        ),
        (
            (
                "TPU: the nodes (in pool test-pool) cannot be created now due"
                " to lack of capacity in your reservation. They will be created"
                " asynchronously once capacity is available. You can either"
                " wait for the nodes to be up, or delete the node pool and try"
                " re-creating it again later"
            ),
            True,
        ),
        ("Generic error message", False),
    ],
)
def test_display_nodepool_creation_error_handles_error_messages(
    mocker, mock_xpk_print, error_message, is_stockout
):
  """Tests that display_nodepool_creation_error surfaces errors and detects stockouts."""

  log_contents = """Operation [
  ...
  ] finished with error: """ + error_message + "\n"
  mocker.patch("builtins.open", mocker.mock_open(read_data=log_contents))
  display_nodepool_creation_error(maybe_failure)

  assert mock_xpk_print.call_count == 3 if is_stockout else 2
  assert (
      mock_xpk_print.call_args_list[0].args[0]
      == "Create Nodepools returned ERROR 1"
  )
  assert (
      mock_xpk_print.call_args_list[1].args[0]
      == "Nodepool creation error: " + error_message
  )
  assert (
      not is_stockout
      or mock_xpk_print.call_args_list[2].args[0]
      == "NOTE: this error might be caused by a stockout"
  )


def test_display_nodepool_creation_ignores_logs_without_errors(
    mocker,
    mock_xpk_print,
):
  """Tests that display_nodepool_creation_error ignores log files with no errors."""

  log_contents = """Operation [
  ...
  ] succeeded!"""
  mocker.patch("builtins.open", mocker.mock_open(read_data=log_contents))
  display_nodepool_creation_error(maybe_failure)

  assert mock_xpk_print.call_count == 1
  assert (
      mock_xpk_print.call_args_list[0].args[0]
      == "Create Nodepools returned ERROR 1"
  )
