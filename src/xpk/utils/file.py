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
import requests


def download_file_from_github(url: str, filepath: str):
  """Download a file from public gh repo to filepath

  Args:
      url (str): url pointing to file in github
      filepath (str): local file to which gh content will be saved
  """
  resp = requests.get(url, timeout=300)
  with open(filepath, 'w+', encoding='utf8') as dockerfile:
    dockerfile.write(resp.text)


def make_tmp_files(per_command_name):
  """Make temporary files for each command.

  Args:
    per_command_name: list of command names.

  Returns:
    A list of temporary files for each command.
  """
  # Supports removal of spaces from command names before converting to file name.
  return [
      tempfile.NamedTemporaryFile(
          delete=False, prefix=command.replace(' ', '-') + '-'
      )
      for command in per_command_name
  ]


def write_tmp_file(payload):
  """Writes `payload` to a temporary file.

  Args:
    payload: The string to be written to the file.

  Returns:
    A file object that was written to.
  """
  with tempfile.NamedTemporaryFile(delete=False) as tmp:
    with open(file=tmp.name, mode='w', encoding='utf=8') as f:
      f.write(payload)
      f.flush()
    return tmp


def append_tmp_file(payload, file):
  """Appends `payload` to an already created file.

  Use `write_temporary_file` to create a file.

  Args:
    payload: The string to be written to the file.
    file: The file to append to.

  Returns:
    A file object that was written to.
  """
  with open(file=file.name, mode='a', encoding='utf=8') as f:
    f.write(payload)
    f.flush()
  return file
