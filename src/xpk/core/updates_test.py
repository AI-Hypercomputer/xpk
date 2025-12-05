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

from ..utils.execution_context import set_dry_run
from .updates import get_latest_xpk_version, print_xpk_hello
from packaging.version import Version
from .config import __version__
from unittest.mock import MagicMock, patch


def test_get_latest_xpk_version_returns_current_version_for_dry_run():
  set_dry_run(True)
  return_code, version = get_latest_xpk_version()
  assert return_code == 0
  assert version == Version(__version__)


@patch('xpk.core.updates.run_command_for_value')
def test_get_latest_xpk_version_returns_error_when_underlaying_command_errors(
    run_command_for_value: MagicMock,
):
  run_command_for_value.return_value = (1, None)
  set_dry_run(False)
  return_code, version = get_latest_xpk_version()
  assert return_code == 1
  assert version is None


@patch('xpk.core.updates.run_command_for_value')
def test_get_latest_xpk_version_returns_version_returned_from_command(
    run_command_for_value: MagicMock,
):
  run_command_for_value.return_value = (0, '{"latest": "1.0.0"}')
  set_dry_run(False)
  return_code, version = get_latest_xpk_version()
  assert return_code == 0
  assert version == Version('1.0.0')


@patch('xpk.core.updates.xpk_print')
@patch('xpk.core.updates.get_latest_xpk_version')
def test_print_xpk_hello_does_not_print_update_when_version_check_fails(
    get_latest_xpk_version: MagicMock, xpk_print: MagicMock
):
  get_latest_xpk_version.return_value = (1, None)
  print_xpk_hello()
  xpk_print.assert_called_once()


@patch('xpk.core.updates.xpk_print')
@patch('xpk.core.updates.get_latest_xpk_version')
def test_print_xpk_hello_does_not_print_update_when_xpk_is_up_to_date(
    get_latest_xpk_version: MagicMock, xpk_print: MagicMock
):
  get_latest_xpk_version.return_value = (0, Version(__version__))
  print_xpk_hello()
  xpk_print.assert_called_once()


@patch('xpk.core.updates.xpk_print')
@patch('xpk.core.updates.get_latest_xpk_version')
def test_print_xpk_hello_prints_update_when_xpk_is_outdated(
    get_latest_xpk_version: MagicMock, xpk_print: MagicMock
):
  get_latest_xpk_version.return_value = (0, Version('99.99.99'))
  print_xpk_hello()
  assert xpk_print.call_count == 2
