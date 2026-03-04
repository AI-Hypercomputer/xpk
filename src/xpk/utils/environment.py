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

import contextlib
import os
from typing import Iterator

from .dependencies.manager import get_dependencies_path


@contextlib.contextmanager
def custom_binaries_path_env(
    custom_binaries_path: str | None = None,
) -> Iterator[None]:
  """Context manager to use a custom binaries path."""
  paths_to_prepend: list[str] = []

  if custom_binaries_path:
    paths_to_prepend.append(custom_binaries_path)

  paths_to_prepend.extend(get_dependencies_path())

  environ = os.environ
  path = environ.get("PATH")
  if path:
    paths_to_prepend.append(path)

  environ["PATH"] = os.pathsep.join(paths_to_prepend)

  try:
    yield
  finally:
    if path is not None:
      environ["PATH"] = path
    else:
      environ.pop("PATH", None)
