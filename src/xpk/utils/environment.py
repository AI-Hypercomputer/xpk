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

import contextlib
import os
from typing import Iterator


@contextlib.contextmanager
def custom_binaries_path_env(
    custom_binaries_path: str | None = None,
) -> Iterator[None]:
  """Context manager to use a custom binaries path."""
  if custom_binaries_path:
    environ = os.environ
    backup = environ.get('PATH')
    environ['PATH'] = (
        f'{custom_binaries_path}{os.pathsep}{backup}'
        if backup is not None
        else custom_binaries_path
    )
    try:
      yield
    finally:
      if backup is None:
        del environ['PATH']
      else:
        environ['PATH'] = backup
  else:
    yield
