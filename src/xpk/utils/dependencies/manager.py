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
from pathlib import Path

from xpk.utils.dependencies.binary_dependencies import BinaryDependencies, BinaryDependency
from xpk.utils.dependencies.downloader import fetch_dependency


def _get_cache_bin_dir() -> Path:
  cache_dir = os.environ.get("XPK_CACHE_HOME", Path.home() / ".cache")
  return Path(cache_dir) / "xpk" / "bin"


def get_dependencies_path() -> list[str]:
  """Returns a list of directories to prepend to PATH."""
  cache_bin = _get_cache_bin_dir()
  return [
      str(cache_bin / f"{dep.name}-{dep.value.version}")
      for dep in BinaryDependencies
  ]


def ensure_dependency(dependency: BinaryDependency) -> bool:
  """Ensures dependency is downloaded."""
  cache_bin = _get_cache_bin_dir()

  version_dir = cache_bin / f"{dependency.binary_name}-{dependency.version}"
  binary_path = version_dir / dependency.binary_name

  if binary_path.exists():
    return True

  return fetch_dependency(
      binary_dependency=dependency,
      target_dir=version_dir,
  )
