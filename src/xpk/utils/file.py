"""
Copyright 2024 Google LLC

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

import tempfile
import os
import hashlib
from .execution_context import is_dry_run
from .console import xpk_print


def make_tmp_files(per_command_name: list[str]) -> list[str]:
  """Make temporary files for each command.

  Args:
    per_command_name: list of command names.

  Returns:
    A list of temporary files for each command.
  """
  if is_dry_run():
    return [_hash_filename(command) for command in per_command_name]

  # Supports removal of spaces from command names before converting to file name.
  return [
      tempfile.NamedTemporaryFile(
          delete=False, prefix=command.replace(' ', '-') + '-'
      ).file.name
      for command in per_command_name
  ]


def write_tmp_file(payload: str) -> str:
  """Writes `payload` to a temporary file.

  Args:
    payload: The string to be written to the file.

  Returns:
    A file object that was written to.
  """
  if is_dry_run():
    name = _hash_filename(payload)
    xpk_print(f'Temp file ({name}) content: \n{payload}')
    return name

  with tempfile.NamedTemporaryFile(delete=False) as tmp:
    with open(file=tmp.name, mode='w', encoding='utf=8') as f:
      f.write(payload)
      f.flush()
    return tmp.file.name


def append_tmp_file(payload: str, file: str) -> str:
  """Appends `payload` to an already created file.

  Use `write_temporary_file` to create a file.

  Args:
    payload: The string to be written to the file.
    file: The file to append to.

  Returns:
    A file object that was written to.
  """
  if is_dry_run():
    return file

  with open(file=file, mode='a', encoding='utf=8') as f:
    f.write(payload)
    f.flush()
  return file


def ensure_directory_exists(directory_path: str) -> None:
  """Checks if a directory exists and creates it if it doesn't.

  Args:
    directory_path: The path to the directory.
  """
  if not is_dry_run() and not os.path.exists(directory_path):
    os.makedirs(directory_path)


def _hash_filename(seed: str) -> str:
  m = hashlib.sha256()
  m.update(seed.encode('utf-8'))
  return m.hexdigest()
