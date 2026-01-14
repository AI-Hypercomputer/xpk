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
from unittest import mock
from xpk.commands import inspector
from xpk.core.testing.commands_tester import CommandsTester


@pytest.fixture
def args():
  args = mock.Mock()
  args.print_to_terminal = False
  return args


@pytest.fixture
def commands_tester(mocker):
  return CommandsTester(
      mocker,
      run_command_for_value_path="xpk.commands.inspector.run_command_for_value",
  )


@pytest.fixture
def mock_has_super_slicing_enabled(mocker):
  return mocker.patch("xpk.commands.inspector.has_super_slicing_enabled")


@pytest.fixture
def mock_append_tmp_file(mocker):
  return mocker.patch("xpk.commands.inspector.append_tmp_file")


@pytest.fixture
def mock_xpk_print(mocker):
  return mocker.patch("xpk.commands.inspector.xpk_print")


def test_inspector_run_slice_controller_helper_no_super_slicing(
    args: mock.Mock,
    commands_tester: CommandsTester,
    mock_has_super_slicing_enabled: mock.Mock,
    mock_append_tmp_file: mock.Mock,
):
  mock_has_super_slicing_enabled.return_value = (0, False)

  inspector.inspector_run_slice_controller_helper(args, "test_file")
  commands_tester.assert_command_not_run(
      "kubectl logs deployment slice-controller-controller-manager"
  )
  commands_tester.assert_command_not_run(
      "kubectl describe deployment slice-controller-controller-manager"
  )
  mock_append_tmp_file.assert_not_called()


def test_inspector_run_slice_controller_helper_with_super_slicing_success(
    args: mock.Mock,
    commands_tester: CommandsTester,
    mock_has_super_slicing_enabled: mock.Mock,
    mock_append_tmp_file: mock.Mock,
):
  commands_tester.set_result_for_command(
      (0, "some logs"),
      "kubectl",
      "logs",
      "deployment slice-controller-controller-manager",
  )
  commands_tester.set_result_for_command(
      (0, "some details"),
      "kubectl",
      "describe",
      "deployment slice-controller-controller-manager",
  )
  mock_has_super_slicing_enabled.return_value = (0, True)

  inspector.inspector_run_slice_controller_helper(args, "test_file")

  commands_tester.assert_command_run(
      "kubectl logs deployment slice-controller-controller-manager"
  )
  commands_tester.assert_command_run(
      "kubectl describe deployment slice-controller-controller-manager"
  )

  mock_append_tmp_file.assert_called()
  call_args_list = mock_append_tmp_file.call_args_list
  assert any(
      "Super-slicing topology set up" in args[0] for args, _ in call_args_list
  )
  assert any("some logs" in args[0] for args, _ in call_args_list)
  assert any("some details" in args[0] for args, _ in call_args_list)


def test_inspector_run_slice_controller_helper_with_slice_controller_not_found(
    args: mock.Mock,
    commands_tester: CommandsTester,
    mock_has_super_slicing_enabled: mock.Mock,
    mock_append_tmp_file: mock.Mock,
    mock_xpk_print: mock.Mock,
):
  commands_tester.set_result_for_command(
      (1, "Error: Deployment not found"),
      "kubectl",
      "deployment slice-controller-controller-manager",
  )
  mock_has_super_slicing_enabled.return_value = (0, True)

  inspector.inspector_run_slice_controller_helper(args, "test_file")

  commands_tester.assert_command_run(
      "kubectl describe deployment slice-controller-controller-manager"
  )
  commands_tester.assert_command_run(
      "kubectl logs deployment slice-controller-controller-manager"
  )

  mock_append_tmp_file.assert_called()
  call_args_list = mock_append_tmp_file.call_args_list
  assert any(
      "Super-slicing topology set up" in args[0] for args, _ in call_args_list
  )

  mock_xpk_print.assert_called()
  call_args_list = mock_xpk_print.call_args_list
  assert any(
      "Error: Deployment not found" in args[0] for args, _ in call_args_list
  )
