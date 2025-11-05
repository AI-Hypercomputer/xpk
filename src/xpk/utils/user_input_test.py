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

from unittest.mock import MagicMock, patch
import pytest
from pytest_mock import MockerFixture

from xpk.utils.user_input import ask_for_user_consent


@pytest.fixture(autouse=True)
def mock_is_quiet(mocker: MockerFixture):
  return mocker.patch("xpk.utils.user_input.is_quiet", return_value=False)


@pytest.mark.parametrize(
    "user_input,expected",
    [
        ("yes", True),
        ("y", True),
        ("Y", True),
        ("Yes", True),
        ("YES", True),
        ("no", False),
        ("n", False),
        ("N", False),
        ("No", False),
        ("NO", False),
    ],
)
@patch("xpk.utils.user_input.input")
def test_ask_for_user_consent(mock_input: MagicMock, user_input, expected):
  mock_input.return_value = user_input

  assert ask_for_user_consent("Test question?") is expected


def fake_input_factory(user_inputs: list[str]):
  def fake_input(prompt: str) -> str:
    return user_inputs.pop(0)

  return fake_input


@patch("xpk.utils.user_input.input", wraps=fake_input_factory(["invalid", "y"]))
def test_ask_for_user_consent_invalid_input(mock_input: MagicMock):
  agreed = ask_for_user_consent("Test question?")

  assert agreed is True
  assert mock_input.call_count == 2


@patch("xpk.utils.user_input.input", return_value="")
def test_ask_for_user_consent_default_No(mock_input: MagicMock):
  agreed = ask_for_user_consent("Test question?", default_option="N")

  assert agreed is False
  mock_input.assert_called_once_with("[XPK] Test question? (y/N): ")


@patch("xpk.utils.user_input.input", return_value="")
def test_ask_for_user_consent_default_Yes(mock_input: MagicMock):
  agreed = ask_for_user_consent("Test question?", default_option="Y")

  assert agreed is True
  mock_input.assert_called_once_with("[XPK] Test question? (Y/n): ")


@patch("xpk.utils.user_input.input")
def test_ask_for_user_consent_with_quiet_mode_always_agrees(
    mock_input: MagicMock,
    mock_is_quiet: MagicMock,
):
  mock_is_quiet.return_value = True

  agreed = ask_for_user_consent("Test question?", default_option="N")

  assert agreed is True
  mock_input.assert_not_called()
