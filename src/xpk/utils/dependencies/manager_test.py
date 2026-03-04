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

import pathlib
import pytest
from pytest_mock import MockerFixture

from xpk.utils.dependencies import manager
from xpk.utils.dependencies.binary_dependencies import BinaryDependencies


def test_get_dependencies_path_default_cache_dir(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
  monkeypatch.delenv('XPK_CACHE_HOME', raising=False)
  paths = manager.get_dependencies_path()
  expected = [
      str(
          pathlib.Path.home()
          / '.cache'
          / 'xpk'
          / 'bin'
          / f'{dep.value.binary_name}-{dep.value.version}'
      )
      for dep in BinaryDependencies
  ]
  assert paths == expected


def test_get_dependencies_path_custom_cache_dir(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
  monkeypatch.setenv('XPK_CACHE_HOME', '/custom/cache')
  paths = manager.get_dependencies_path()
  expected = [
      str(
          pathlib.Path('/custom/cache')
          / 'xpk'
          / 'bin'
          / f'{dep.value.binary_name}-{dep.value.version}'
      )
      for dep in BinaryDependencies
  ]
  assert paths == expected


def test_ensure_dependency_already_exists(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    mocker: MockerFixture,
) -> None:
  monkeypatch.setenv('XPK_CACHE_HOME', str(tmp_path))

  dep = BinaryDependencies.KUBECTL.value

  # Setup the file system so the dependency appears as already downloaded
  version_dir = tmp_path / 'xpk' / 'bin' / f'{dep.binary_name}-{dep.version}'
  version_dir.mkdir(parents=True)
  binary_path = version_dir / dep.binary_name
  binary_path.touch()

  mock_fetch = mocker.patch('xpk.utils.dependencies.manager.fetch_dependency')

  result = manager.ensure_dependency(dep)

  assert result is True
  mock_fetch.assert_not_called()


def test_ensure_dependency_needs_download(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    mocker: MockerFixture,
) -> None:
  monkeypatch.setenv('XPK_CACHE_HOME', str(tmp_path))

  dep = BinaryDependencies.KUBECTL.value

  mock_fetch = mocker.patch('xpk.utils.dependencies.manager.fetch_dependency')
  mock_fetch.return_value = True

  result = manager.ensure_dependency(dep)

  assert result is True

  expected_version_dir = (
      tmp_path / 'xpk' / 'bin' / f'{dep.binary_name}-{dep.version}'
  )
  mock_fetch.assert_called_once_with(
      binary_dependency=dep, target_dir=expected_version_dir
  )
