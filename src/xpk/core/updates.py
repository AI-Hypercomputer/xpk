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

import json
from json.decoder import JSONDecodeError
from .commands import run_command_for_value
from ..utils.console import xpk_print
from ..utils.execution_context import is_dry_run
from packaging.version import Version
from .config import __version__


def get_latest_xpk_version() -> tuple[int, Version | None]:
  if is_dry_run():
    return 0, Version(__version__)

  return_code, result = run_command_for_value(
      command="pip index versions xpk --json --no-input",
      task="Retrieve latest XPK version",
      quiet=True,
  )

  if return_code != 0:
    return return_code, None

  try:
    parsed = json.loads(result.strip())
    return 0, Version(parsed["latest"])
  except JSONDecodeError:
    return 1, None


def print_xpk_hello() -> None:
  current_version = Version(__version__)
  xpk_print(f"Starting xpk v{current_version}", flush=True)
  return_code, latest_version = get_latest_xpk_version()
  if return_code != 0 or latest_version is None:
    return
  if current_version < latest_version:
    xpk_print(
        f"XPK version v{current_version} is outdated. Please consider upgrading"
        f" to v{latest_version}",
        flush=True,
    )
