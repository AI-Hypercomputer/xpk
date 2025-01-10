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

import hashlib
from .console import xpk_print


def chunks(lst: list, n: int):
  """Return a list of n-sized chunks from lst.

  Args:
    lst: input list to get chunks from.
    n: size of each chunk.

  Returns:
    List of n-sized chunks for lst.
  """
  return [lst[i : i + n] for i in range(0, len(lst), n)]


def get_value_from_map(
    key: str, map_to_search: dict, verbose: bool = True
) -> tuple[int, str | None]:
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
    if verbose:
      xpk_print(
          f'Unable to find key: {key} in map: {map_to_search}.'
          f'The map has the following keys: {map_to_search.keys()}'
      )
    return 1, value


def is_text_true(text: str) -> bool:
  return text.strip().lower() == 'true'


def hash_string(input_string: str, length: int | None = None):
  """
  Generates a hash of a string using characters 0-9 and a-z.

  Args:
    input_string: The string to hash.
    length: The desired length of the hash (optional).
            If not provided, or less than 0, the full SHA256 hash is returned.

  Returns:
    A hash string of the specified length or the full SHA256 hash,
    using characters 0-9 and a-z.
  """
  hash_value = int(hashlib.sha256(input_string.encode()).hexdigest(), 16)

  if length is None or length < 0:
    length = 64  # Use the full length of the SHA256 hash

  charset = '0123456789abcdefghijklmnopqrstuvwxyz'
  result = ''
  while hash_value > 0 and len(result) < length:
    hash_value, index = divmod(hash_value, 36)  # Get quotient and remainder
    result = charset[index] + result

  return result.zfill(length).lower()  # Pad with zeros if necessary
