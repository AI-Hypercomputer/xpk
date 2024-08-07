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

import argparse
import os
import re
import sys
import tempfile


def chunks(lst: list, n: int):
  """Return a list of n-sized chunks from lst.

  Args:
    lst: input list to get chunks from.
    n: size of each chunk.

  Returns:
    List of n-sized chunks for lst.
  """
  return [lst[i : i + n] for i in range(0, len(lst), n)]


def get_value_from_map(key: str, map_to_search: dict) -> tuple[int, str | None]:
  """Helper function to get value from a map if the key exists.

  Args:
    key: The key to look for in the map
    map_to_search: The map to look in for the value

  Returns:
    Tuple of int, str where
    int is the return code
    str is the value if found
  """
  value = map_to_search.get(key)
  if value:
    return 0, value
  else:
    xpk_print(
        f'Unable to find key: {key} in map: {map_to_search}.'
        f'The map has the following keys: {map_to_search.keys()}'
    )
    return 1, value


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


def xpk_print(*args, **kwargs):
  """Helper function to print a prefix before function provided args.

  Args:
    *args: user provided print args.
    **kwargs: user provided print args.
  """
  sys.stdout.write('[XPK] ')
  print(*args, **kwargs)
  sys.stdout.flush()


def xpk_exit(error_code):
  """Helper function to exit xpk with an associated error code.

  Args:
    error_code: If the code provided is zero, then no issues occurred.
  """
  if error_code == 0:
    xpk_print('Exiting XPK cleanly')
    sys.exit(0)
  else:
    xpk_print(f'XPK failed, error code {error_code}')
    sys.exit(error_code)


def get_user_input(input_msg):
  """Function to get the user input for a prompt.

  Args:
    input_msg: message to be displayed by the prompt.
  Returns:
    True if user enter y or yes at the prompt, False otherwise.
  """
  user_input = input(input_msg)
  return user_input in ('y', 'yes')


def workload_name_type(value, pat=re.compile(r'[a-z]([-a-z0-9]*[a-z0-9])?')):
  """Validate that the workload name matches the expected pattern."""
  match = pat.fullmatch(value)
  if not match or len(match.group(0)) > 40:
    raise argparse.ArgumentTypeError(
        'Workload name must be less than 40 characters and match the pattern'
        f' `{pat.pattern}`'
        f' Name is currently {value}'
    )
  return value


def directory_path_type(value):
  if not os.path.isdir(value):
    raise argparse.ArgumentTypeError(
        f'Directory path is invalid. User provided path was {value}'
    )
  return value
