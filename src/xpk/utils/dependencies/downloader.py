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

import shutil
import hashlib
import os
import tempfile
import platform
import urllib.error
import urllib.parse
import urllib.request
import pathlib

from xpk.utils.console import xpk_print
from xpk.utils.dependencies.binary_dependencies import BinaryDependency


_OS_MAP: dict[str, str] = {"Linux": "linux", "Darwin": "darwin"}
_ARCH_MAP: dict[str, str] = {
    "x86_64": "amd64",
    "aarch64": "arm64",
    "arm64": "arm64",
}


def _get_os_and_arch() -> tuple[str | None, str | None]:
  """Detects the current operating system and architecture."""
  return _OS_MAP.get(platform.system()), _ARCH_MAP.get(platform.machine())


def _get_checksum(
    binary_dependency: BinaryDependency, os_name: str, arch_name: str
) -> str | None:
  """Retrieves the expected checksum for the given OS and architecture."""
  return binary_dependency.checksums.get(f"{os_name}_{arch_name}")


def _format_url(
    binary_dependency: BinaryDependency, os_name: str, arch_name: str
) -> str:
  """Formats the download URL based on OS and architecture."""
  mapped_arch = binary_dependency.arch_map.get(arch_name, arch_name)
  return binary_dependency.url_template.format(
      version=binary_dependency.version,
      os=os_name,
      arch=mapped_arch,
      os_capitalized=os_name.capitalize(),
  )


def _download_file(url: str, path: pathlib.Path, name: str) -> bool:
  """Downloads a file from a URL to a local path."""
  try:
    xpk_print(f"Downloading {url} ...")
    with urllib.request.urlopen(url) as response, open(path, "wb") as f:
      shutil.copyfileobj(response, f)
    return True
  except urllib.error.HTTPError as e:
    xpk_print(f"Error downloading {name}: HTTP {e.code} - {e.reason}")
    return False
  except urllib.error.URLError as e:
    xpk_print(f"Error downloading {name}: {e}")
    return False


def _verify_checksum(
    path: pathlib.Path, expected_checksum: str, name: str
) -> bool:
  """Verifies the SHA-256 checksum of a file."""
  sha256 = hashlib.sha256()
  with open(path, "rb") as f:
    while chunk := f.read(65536):
      sha256.update(chunk)

  if sha256.hexdigest() != expected_checksum:
    xpk_print(
        f"Error: Checksum mismatch for {name}. Download might be corrupted."
    )
    return False
  return True


def _extract_archive(
    archive_path: pathlib.Path, extract_dir: pathlib.Path, name: str
) -> bool:
  """Extracts an archive to the specified directory."""
  try:
    shutil.unpack_archive(archive_path, extract_dir, filter="data")
    return True
  except (shutil.ReadError, OSError, ValueError) as e:
    xpk_print(f"Error extracting archive for {name}: {e}")
    return False


def _install_binary(src_path: pathlib.Path, target_path: pathlib.Path) -> None:
  """Moves the binary to the target path and makes it executable."""
  os.makedirs(os.path.dirname(target_path), exist_ok=True)
  shutil.move(src_path, target_path)
  os.chmod(target_path, 0o755)


def _process_downloaded_file(
    binary_dependency: BinaryDependency,
    download_path: pathlib.Path,
    temp_dir: pathlib.Path,
    final_path: pathlib.Path,
) -> bool:
  """Handles extraction (if needed) and installation of the downloaded file."""
  if binary_dependency.archive_type == "binary":
    _install_binary(download_path, final_path)
    return True

  if not _extract_archive(
      download_path, temp_dir, binary_dependency.binary_name
  ):
    return False

  matches = list(pathlib.Path(temp_dir).rglob(binary_dependency.binary_name))
  if not matches:
    xpk_print(f"Error: {binary_dependency.binary_name} not found in archive.")
    return False

  _install_binary(matches[0], final_path)
  return True


def fetch_dependency(
    binary_dependency: BinaryDependency,
    target_dir: pathlib.Path,
) -> bool:
  """Fetches, verifies, and installs a binary dependency."""
  os_name, arch_name = _get_os_and_arch()
  if not os_name or not arch_name:
    xpk_print(
        "Warning: Unsupported OS or Architecture for auto-downloading"
        " dependencies."
    )
    return False

  xpk_print(
      f"Fetching dependency {binary_dependency.binary_name} for"
      f" {os_name}/{arch_name}..."
  )

  expected_checksum = _get_checksum(binary_dependency, os_name, arch_name)
  if not expected_checksum:
    xpk_print(
        f"Warning: No checksum found for {binary_dependency.binary_name} on"
        f" {os_name}/{arch_name}"
    )
    return False

  url = _format_url(binary_dependency, os_name, arch_name)

  with tempfile.TemporaryDirectory() as temp_dir:
    temp_dir_path = pathlib.Path(temp_dir)
    filename = pathlib.Path(urllib.parse.urlparse(url).path).name
    download_path = temp_dir_path / filename

    if not _download_file(url, download_path, binary_dependency.binary_name):
      return False

    if not _verify_checksum(
        download_path, expected_checksum, binary_dependency.binary_name
    ):
      return False

    final_path = target_dir / binary_dependency.binary_name
    return _process_downloaded_file(
        binary_dependency, download_path, temp_dir_path, final_path
    )
