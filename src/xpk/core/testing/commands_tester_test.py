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
from pytest_mock import MockerFixture

from xpk.core.commands import run_command_for_value, run_command_with_updates_retry
from xpk.core.testing.commands_tester import CommandsTester


@pytest.fixture
def mock_commands(mocker: MockerFixture) -> CommandsTester:
  return CommandsTester(
      mocker,
      run_command_for_value_path=(
          "xpk.core.testing.commands_tester_test.run_command_for_value"
      ),
      run_command_with_updates_retry_path=(
          "xpk.core.testing.commands_tester_test.run_command_with_updates_retry"
      ),
  )


def test_run_for_value_default_result(mock_commands: CommandsTester):
  result = run_command_for_value(
      command="cmd foo bar baz qux", task="Test command"
  )

  assert result == (0, "0")
  mock_commands.assert_command_run("cmd", "bar")


def test_run_command_with_updates_retry_default_result(
    mock_commands: CommandsTester,
):
  result = run_command_with_updates_retry(
      command="cmd foo bar baz qux", task="Test command"
  )

  assert result == 0
  mock_commands.assert_command_run("cmd", "bar")


def test_set_result_for_command(mock_commands: CommandsTester):
  mock_commands.set_result_for_command((17, "Error!"), "cmd", "--err")

  result = run_command_for_value("cmd foo --err", task="Matching test command")

  assert result == (17, "Error!")


def test_set_result_for_command_not_matching_other_commands(
    mock_commands: CommandsTester,
):
  mock_commands.set_result_for_command((17, "Error!"), "cmd", "--err")

  result = run_command_for_value(
      "cmd foo bar", task="Not matching test command"
  )

  assert result == (0, "0")


def test_assert_command_run(mock_commands: CommandsTester):
  run_command_for_value("cmd foo bar", task="Test command")

  mock_commands.assert_command_run("cmd foo bar")
  mock_commands.assert_command_run("cmd")
  mock_commands.assert_command_run("cmd", "bar")


def test_assert_command_run_twice(mock_commands: CommandsTester):
  run_command_for_value("cmd foo bar", task="Test command")
  run_command_for_value("cmd foo bar", task="Test command")

  mock_commands.assert_command_run("cmd", times=2)


def test_assert_command_not_run(mock_commands: CommandsTester):
  run_command_for_value("cmd", task="Test command")

  mock_commands.assert_command_not_run("kubectl")


def test_commands_history_contains_all_commands_in_order(
    mock_commands: CommandsTester,
):
  run_command_for_value("cmd1", task="Test command")
  run_command_for_value("cmd2 foo", task="Test command2")
  run_command_for_value("cmd3 bar", task="Test command3")

  assert mock_commands.commands_history == [
      "cmd1",
      "cmd2 foo",
      "cmd3 bar",
  ]


def test_get_matching_commands(mock_commands: CommandsTester):
  run_command_for_value("cmd", task="Test command")
  run_command_for_value("cmd foo", task="Test command")
  run_command_for_value("cmd foo bar", task="Test command")

  assert len(mock_commands.get_matching_commands("cmd")) == 3
  assert len(mock_commands.get_matching_commands("cmd", "foo")) == 2
  assert mock_commands.get_matching_commands("cmd", "bar") == ["cmd foo bar"]


def test_get_matching_commands_matches_parts_substrings(
    mock_commands: CommandsTester,
):
  run_command_for_value("kubectl apply", task="Test command")
  run_command_for_value("kubectl", task="Test command")

  assert len(mock_commands.get_matching_commands("kube")) == 2
  assert len(mock_commands.get_matching_commands("ctl apply")) == 1
