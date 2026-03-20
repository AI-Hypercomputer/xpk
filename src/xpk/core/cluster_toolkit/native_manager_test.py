"""Tests for native_manager.py."""

import os
from unittest import mock
import pytest

from xpk.core.cluster_toolkit.native_manager import NativeCommandRunner
from xpk.utils.dependencies.binary_dependencies import BinaryDependencies


@pytest.fixture
def runner():
  return NativeCommandRunner(working_dir="/fake/working_dir")


@mock.patch("xpk.core.cluster_toolkit.native_manager.xpk_print")
@mock.patch("xpk.core.cluster_toolkit.native_manager.ensure_dependency")
def test_initialize_success(mock_ensure, mock_print, runner):
  mock_ensure.return_value = True

  runner.initialize()

  mock_ensure.assert_called_once_with(BinaryDependencies.GCLUSTER.value)
  mock_print.assert_any_call("Initializing native command runner...")
  mock_print.assert_any_call("gcluster dependency ensured.")


@mock.patch("xpk.core.cluster_toolkit.native_manager.xpk_exit")
@mock.patch("xpk.core.cluster_toolkit.native_manager.xpk_print")
@mock.patch("xpk.core.cluster_toolkit.native_manager.ensure_dependency")
def test_initialize_failure(mock_ensure, mock_print, mock_exit, runner):
  mock_ensure.return_value = False

  runner.initialize()

  mock_ensure.assert_called_once_with(BinaryDependencies.GCLUSTER.value)
  mock_print.assert_any_call("Failed to ensure gcluster dependency.")
  mock_exit.assert_called_once_with(1)


@mock.patch(
    "xpk.core.cluster_toolkit.native_manager.run_command_with_full_controls"
)
def test_run_command_success(mock_run, runner):
  mock_run.return_value = 0

  runner.run_command("echo hello")

  mock_run.assert_called_once_with(
      command="echo hello",
      task="gcluster execution",
  )


@mock.patch("xpk.core.cluster_toolkit.native_manager.xpk_exit")
@mock.patch("xpk.core.cluster_toolkit.native_manager.xpk_print")
@mock.patch(
    "xpk.core.cluster_toolkit.native_manager.run_command_with_full_controls"
)
def test_run_command_failure(mock_run, mock_print, mock_exit, runner):
  mock_run.return_value = 123

  runner.run_command("echo hello")

  mock_run.assert_called_once_with(
      command="echo hello",
      task="gcluster execution",
  )
  mock_print.assert_any_call(
      "Running gcluster command: echo hello failed with code 123."
  )
  mock_exit.assert_called_once_with(123)


def test_get_deployment_dir_no_prefix(runner):
  assert runner.get_deployment_dir() == "/fake/working_dir"


def test_get_deployment_dir_with_prefix(runner):
  assert runner.get_deployment_dir("my-prefix") == "/fake/working_dir/my-prefix"


@mock.patch("xpk.core.cluster_toolkit.native_manager.copytree")
@mock.patch("xpk.core.cluster_toolkit.native_manager.ensure_directory_exists")
@mock.patch("xpk.core.cluster_toolkit.native_manager.xpk_print")
def test_upload_directory_to_working_dir(
    mock_print, mock_ensure, mock_copytree, runner
):
  result = runner.upload_directory_to_working_dir(
      "/path/to/my_dir", prefix="pre"
  )

  expected_upload_dir = os.path.join("/fake/working_dir", "uploads", "pre")
  expected_target_path = os.path.join(expected_upload_dir, "my_dir")

  mock_ensure.assert_called_once_with(expected_upload_dir)
  mock_copytree.assert_called_once_with(
      "/path/to/my_dir", expected_target_path, dirs_exist_ok=True
  )
  mock_print.assert_any_call(
      f"Copying directory from /path/to/my_dir to {expected_target_path}."
  )
  assert result == expected_target_path


@mock.patch("xpk.core.cluster_toolkit.native_manager.copytree")
@mock.patch("xpk.core.cluster_toolkit.native_manager.ensure_directory_exists")
def test_upload_directory_to_working_dir_no_prefix(
    mock_ensure, mock_copytree, runner
):
  result = runner.upload_directory_to_working_dir("/path/to/my_dir")

  expected_upload_dir = os.path.join("/fake/working_dir", "uploads", "")
  expected_target_path = os.path.join(expected_upload_dir, "my_dir")

  mock_ensure.assert_called_once_with(expected_upload_dir)
  mock_copytree.assert_called_once_with(
      "/path/to/my_dir", expected_target_path, dirs_exist_ok=True
  )
  assert result == expected_target_path


@mock.patch("xpk.core.cluster_toolkit.native_manager.copy")
@mock.patch("xpk.core.cluster_toolkit.native_manager.ensure_directory_exists")
@mock.patch("xpk.core.cluster_toolkit.native_manager.xpk_print")
def test_upload_file_to_working_dir(mock_print, mock_ensure, mock_copy, runner):
  result = runner.upload_file_to_working_dir(
      "/path/to/my_file.txt", prefix="pre"
  )

  expected_upload_dir = os.path.join("/fake/working_dir", "uploads", "pre")
  expected_target_path = os.path.join(expected_upload_dir, "my_file.txt")

  mock_ensure.assert_called_once_with(expected_upload_dir)
  mock_copy.assert_called_once_with(
      "/path/to/my_file.txt", expected_target_path
  )
  mock_print.assert_any_call(
      f"Copying a file from /path/to/my_file.txt to {expected_target_path}."
  )
  assert result == expected_target_path


@mock.patch("xpk.core.cluster_toolkit.native_manager.copy")
@mock.patch("xpk.core.cluster_toolkit.native_manager.ensure_directory_exists")
def test_upload_file_to_working_dir_no_prefix(mock_ensure, mock_copy, runner):
  result = runner.upload_file_to_working_dir("/path/to/my_file.txt")

  expected_upload_dir = os.path.join("/fake/working_dir", "uploads", "")
  expected_target_path = os.path.join(expected_upload_dir, "my_file.txt")

  mock_ensure.assert_called_once_with(expected_upload_dir)
  mock_copy.assert_called_once_with(
      "/path/to/my_file.txt", expected_target_path
  )
  assert result == expected_target_path
