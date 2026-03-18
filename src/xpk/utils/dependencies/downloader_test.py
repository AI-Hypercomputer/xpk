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

import hashlib
import io
import os
import pathlib
import tarfile
import urllib.error
from typing import Any
import pytest

from xpk.utils.dependencies.binary_dependencies import BinaryDependency
from xpk.utils.dependencies import downloader

# Some fake binary content and its SHA256 sum
FAKE_BINARY_CONTENT = b'fake binary content'
FAKE_BINARY_SHA256 = hashlib.sha256(FAKE_BINARY_CONTENT).hexdigest()


def create_fake_archive(binary_name: str, content: bytes) -> bytes:
  """Creates a gzipped tar archive containing a single file."""
  f = io.BytesIO()
  with tarfile.open(fileobj=f, mode='w:gz') as t:
    ti = tarfile.TarInfo(binary_name)
    ti.size = len(content)
    t.addfile(ti, io.BytesIO(content))
  return f.getvalue()


FAKE_ARCHIVE_CONTENT = create_fake_archive(
    'dummy_archive_bin', FAKE_BINARY_CONTENT
)
FAKE_ARCHIVE_SHA256 = hashlib.sha256(FAKE_ARCHIVE_CONTENT).hexdigest()


class MockResponse:
  """A mock response for urllib.request.urlopen."""

  def __init__(self, data: bytes) -> None:
    self.data = io.BytesIO(data)

  def read(self, *args: Any, **kwargs: Any) -> bytes:
    return self.data.read(*args, **kwargs)

  def __enter__(self) -> 'MockResponse':
    return self

  def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
    pass


@pytest.fixture(autouse=True)
def mock_platform(monkeypatch: pytest.MonkeyPatch) -> None:
  monkeypatch.setattr(
      'xpk.utils.dependencies.downloader.platform.system', lambda: 'Linux'
  )
  monkeypatch.setattr(
      'xpk.utils.dependencies.downloader.platform.machine', lambda: 'x86_64'
  )


@pytest.fixture
def dummy_dependency() -> BinaryDependency:
  return BinaryDependency(
      archive_type='binary',
      binary_name='dummy_bin',
      checksums={
          'linux_amd64': FAKE_BINARY_SHA256,
          'darwin_arm64': FAKE_BINARY_SHA256,
      },
      url_template='https://example.com/{version}/{os}/{arch}/{os}/{arch}',
      arch_map={'amd64': 'x86_64', 'arm64': 'arm64'},
      os_map={'darwin': 'mac'},
      version='v1.0.0',
  )


@pytest.fixture
def dummy_archive_dependency() -> BinaryDependency:
  return BinaryDependency(
      archive_type='tar.gz',
      binary_name='dummy_archive_bin',
      checksums={
          'linux_amd64': FAKE_ARCHIVE_SHA256,
      },
      url_template='https://example.com/{version}/archive.tar.gz',
      version='v1.0.0',
  )


def set_download_content(
    monkeypatch: pytest.MonkeyPatch, content: bytes
) -> None:
  """Helper to mock the response of urlopen."""
  monkeypatch.setattr(
      'xpk.utils.dependencies.downloader.urllib.request.urlopen',
      lambda *args, **kwargs: MockResponse(content),
  )


def test_fetch_dependency_binary_success(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    dummy_dependency: BinaryDependency,
) -> None:
  set_download_content(monkeypatch, FAKE_BINARY_CONTENT)
  target_dir = tmp_path / 'target_bin'

  result = downloader.fetch_dependency(dummy_dependency, target_dir)

  assert result is True
  final_path = target_dir / 'dummy_bin'
  assert final_path.exists()
  with open(final_path, 'rb') as f:
    assert f.read() == FAKE_BINARY_CONTENT
  assert os.access(final_path, os.X_OK)


def test_fetch_dependency_archive_success(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    dummy_archive_dependency: BinaryDependency,
) -> None:
  set_download_content(monkeypatch, FAKE_ARCHIVE_CONTENT)
  target_dir = tmp_path / 'target_archive'

  result = downloader.fetch_dependency(dummy_archive_dependency, target_dir)

  assert result is True
  final_path = target_dir / 'dummy_archive_bin'
  assert final_path.exists()
  with open(final_path, 'rb') as f:
    assert f.read() == FAKE_BINARY_CONTENT
  assert os.access(final_path, os.X_OK)


def test_fetch_dependency_unsupported_os(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    dummy_dependency: BinaryDependency,
) -> None:
  monkeypatch.setattr(
      'xpk.utils.dependencies.downloader.platform.system', lambda: 'Windows'
  )
  monkeypatch.setattr(
      'xpk.utils.dependencies.downloader.platform.machine', lambda: 'x86_64'
  )
  result = downloader.fetch_dependency(dummy_dependency, tmp_path)
  assert result is False


def test_fetch_dependency_no_checksum(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    dummy_archive_dependency: BinaryDependency,
) -> None:
  monkeypatch.setattr(
      'xpk.utils.dependencies.downloader.platform.system', lambda: 'Darwin'
  )
  monkeypatch.setattr(
      'xpk.utils.dependencies.downloader.platform.machine', lambda: 'arm64'
  )
  # The dependency doesn't have checksum for darwin_arm64 in dummy_archive_dependency
  result = downloader.fetch_dependency(dummy_archive_dependency, tmp_path)
  assert result is False


def test_fetch_dependency_download_failure(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    dummy_dependency: BinaryDependency,
) -> None:
  def raise_exception(*args: Any, **kwargs: Any) -> None:
    raise urllib.error.URLError('Network error')

  monkeypatch.setattr(
      'xpk.utils.dependencies.downloader.urllib.request.urlopen',
      raise_exception,
  )
  result = downloader.fetch_dependency(dummy_dependency, tmp_path)
  assert result is False


def test_fetch_dependency_checksum_failure(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    dummy_dependency: BinaryDependency,
) -> None:
  set_download_content(monkeypatch, b'corrupted content')
  result = downloader.fetch_dependency(dummy_dependency, tmp_path)
  assert result is False


def test_fetch_dependency_archive_missing_bin(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
  # Create an archive that doesn't contain the expected binary name
  bad_archive_content = create_fake_archive(
      'wrong_name_bin', FAKE_BINARY_CONTENT
  )
  set_download_content(monkeypatch, bad_archive_content)

  bad_archive_sha256 = hashlib.sha256(bad_archive_content).hexdigest()
  bad_archive_dependency = BinaryDependency(
      archive_type='tar.gz',
      binary_name='dummy_archive_bin',
      checksums={
          'linux_amd64': bad_archive_sha256,
      },
      url_template='https://example.com/archive.tar.gz',
      version='v1.0.0',
  )

  result = downloader.fetch_dependency(bad_archive_dependency, tmp_path)
  assert result is False


def test_fetch_dependency_archive_extract_failure(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
  corrupted_archive_content = b'corrupted archive content'
  set_download_content(monkeypatch, corrupted_archive_content)

  corrupted_archive_sha256 = hashlib.sha256(
      corrupted_archive_content
  ).hexdigest()
  corrupted_archive_dependency = BinaryDependency(
      archive_type='tar.gz',
      binary_name='dummy_archive_bin',
      checksums={
          'linux_amd64': corrupted_archive_sha256,
      },
      url_template='https://example.com/archive.tar.gz',
      version='v1.0.0',
  )

  result = downloader.fetch_dependency(corrupted_archive_dependency, tmp_path)
  assert result is False
