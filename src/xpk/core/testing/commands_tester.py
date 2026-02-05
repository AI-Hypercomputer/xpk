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

import re
from pytest_mock import MockerFixture

from ..commands import FailedCommand


class CommandsTester:
  """Tester class useful for mocking and asserting command runs."""

  def __init__(
      self,
      mocker: MockerFixture,
  ):
    self.__results: dict[re.Pattern, tuple[int, str]] = {}
    self.commands_history: list[str] = []

    self.__fake_functions = {
        "run_command_for_value": self.__fake_run_command_for_value,
        "run_command_with_updates": self.__fake_run_command_with_updates,
        "run_command_with_updates_retry": (
            self.__fake_run_command_with_updates_retry
        ),
        "run_command_batch": self.__fake_run_command_batch,
        "run_command_with_full_controls": (
            self.__fake_run_command_with_full_controls
        ),
    }

    # Auto-patching: find all xpk modules and patch the command functions if they exist.
    import sys

    for module_name, module in list(sys.modules.items()):
      if module_name.startswith("xpk") or module_name.startswith("src.xpk"):
        for func_name, fake_func in self.__fake_functions.items():
          if hasattr(module, func_name):
            mocker.patch.object(module, func_name, wraps=fake_func)

  def set_result_for_command(
      self, result: tuple[int, str], *command_parts: str
  ):
    """Sets the result for the given command parts.
    The command parts will be joined with '.*' during comparison with the actual commands.
    """
    pattern = self.__get_pattern_for_command_parts(*command_parts)
    self.__results[pattern] = result

  def assert_command_run(self, *command_parts: str, times: int = 1):
    """Asserts the command composed from the command parts (joined with '.*') was run exactly `times` times."""
    matching = self.get_matching_commands(*command_parts)
    if not matching:
      raise AssertionError(
          f"{command_parts} was not found in {self.commands_history}"
      )
    elif len(matching) != times:
      raise AssertionError(
          f"{command_parts} was expected to be run {times} times in"
          f" {self.commands_history}"
      )

  def assert_command_not_run(self, *command_parts: str):
    """Asserts the command composed from the command parts (joined with '.*') was never run."""
    if self.get_matching_commands(*command_parts):
      raise AssertionError(
          f"{command_parts} was found in {self.commands_history}"
      )

  def get_matching_commands(self, *command_parts: str) -> list[str]:
    """Returns list of already run commands matching the command parts (joined with '.*')."""
    pattern = self.__get_pattern_for_command_parts(*command_parts)
    return [c for c in self.commands_history if pattern.match(c)]

  # Unused arguments, but the signature has to match the original one:
  # pylint: disable=unused-argument
  def __fake_run_command_with_updates(
      self,
      command: str,
      task: str,
      verbose=True,
  ) -> int:
    return self.__common_fake_run_command(command, (0, ""))[0]

  def __fake_run_command_with_updates_retry(
      self,
      command: str,
      task: str,
      verbose=True,
      num_retry_attempts=5,
      wait_seconds=10,
  ) -> int:
    return self.__common_fake_run_command(command, (0, ""))[0]

  def __fake_run_command_for_value(
      self,
      command: str,
      task: str,
      dry_run_return_val="0",
      print_timer=False,
      hide_error=False,
      quiet=False,
  ) -> tuple[int, str]:
    return self.__common_fake_run_command(command, (0, dry_run_return_val))

  def __fake_run_command_batch(
      self,
      commands: list[str],
      jobname: str,
      per_command_name: list[str],
      output_logs: list[str],
  ) -> FailedCommand | None:
    for i, command in enumerate(commands):
      result = self.__common_fake_run_command(command, (0, ""))[0]
      if result != 0:
        return FailedCommand(
            return_code=result,
            name=per_command_name[i],
            command=command,
            logfile=output_logs[i],
        )
    return None

  def __fake_run_command_with_full_controls(
      self,
      command: str,
      task: str,
      instructions: str | None = None,
  ) -> int:
    return self.__common_fake_run_command(command, (0, ""))[0]

  # pylint: enable=unused-argument

  def __common_fake_run_command(
      self,
      command: str,
      default_result: tuple[int, str],
  ) -> tuple[int, str]:
    self.commands_history.append(command)
    matching_results = [
        result
        for pattern, result in self.__results.items()
        if pattern.match(command)
    ]
    return len(matching_results) > 0 and matching_results[0] or default_result

  def __get_pattern_for_command_parts(self, *command_parts: str) -> re.Pattern:
    pattern_s = ".*" + ".*".join(map(re.escape, command_parts)) + ".*"
    return re.compile(pattern_s)
