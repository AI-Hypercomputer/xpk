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

dry_run = False
quiet = False


def set_context(dry_run_value: bool, quiet_value: bool) -> None:
  """Sets the dry_run and quiet flags."""
  set_dry_run(dry_run_value)
  set_quiet(quiet_value)


def set_dry_run(dry_run_value: bool) -> None:
  """Sets the dry_run flag."""
  global dry_run
  dry_run = dry_run_value


def set_quiet(quiet_value: bool) -> None:
  """Sets the quiet flag."""
  global quiet
  quiet = quiet_value


def is_dry_run() -> bool:
  """Returns the current value of the dry_run flag."""
  return dry_run


def is_quiet() -> bool:
  """Returns the current value of the quiet flag."""
  return quiet
