"""
Copyright 2026 Google LLC

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

import os
from unittest import mock

import pytest

from xpk.utils.environment import custom_binaries_path_env


@pytest.fixture(autouse=True)
def mock_get_dependencies_path():
  with mock.patch("xpk.utils.environment.get_dependencies_path") as mock_get:
    mock_get.return_value = ["/mock/dep/path1", "/mock/dep/path2"]
    yield mock_get


def test_custom_binaries_path_provided():
  """Test custom_binaries_path prepended along with dependencies to PATH."""
  original_path = "/usr/bin:/bin"
  with mock.patch.dict(os.environ, {"PATH": original_path}):
    with custom_binaries_path_env("/my/custom/path"):
      expected_path = os.pathsep.join([
          "/my/custom/path",
          "/mock/dep/path1",
          "/mock/dep/path2",
          original_path,
      ])
      assert os.environ["PATH"] == expected_path

    assert os.environ["PATH"] == original_path


def test_no_custom_binaries_path():
  """Test when no custom_binaries_path is provided, only dependencies prepended."""
  original_path = "/usr/bin:/bin"
  with mock.patch.dict(os.environ, {"PATH": original_path}):
    with custom_binaries_path_env():
      expected_path = os.pathsep.join([
          "/mock/dep/path1",
          "/mock/dep/path2",
          original_path,
      ])
      assert os.environ["PATH"] == expected_path

    assert os.environ["PATH"] == original_path


def test_original_path_empty():
  """Test behavior when PATH is initially empty."""
  with mock.patch.dict(os.environ, {"PATH": ""}):
    with custom_binaries_path_env("/my/custom/path"):
      expected_path = os.pathsep.join([
          "/my/custom/path",
          "/mock/dep/path1",
          "/mock/dep/path2",
      ])
      assert os.environ["PATH"] == expected_path

    assert os.environ["PATH"] == ""


def test_restores_path_on_exception():
  """Test that original path is restored even if an exception occurs."""
  original_path = "/usr/bin:/bin"
  with mock.patch.dict(os.environ, {"PATH": original_path}):
    try:
      with custom_binaries_path_env("/my/custom/path"):
        raise ValueError("Some error")
    except ValueError:
      pass

    assert os.environ["PATH"] == original_path
