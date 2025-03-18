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

from ..core.config import __version__
from ..utils.console import xpk_print, xpk_exit
from ..core.commands import run_command_for_value
import importlib.metadata as importlib_metadata
import os


def get_xpk_version() -> str:
  return __version__


def version(args) -> None:  # pylint: disable=unused-argument
  """Get version of xpk."""
  xpk_version = __version__
  git_hash = ''

  if os.path.exists(os.path.join(os.getcwd(), '.git')):
    code, git_hash = run_command_for_value(
        'git rev-parse HEAD',
        task='Get latest hash',
        global_args=args,
        quiet=True,
    )
    if code != 0:
      xpk_exit(code)
  else:
    xpk_version, git_hash = importlib_metadata.version('xpk').split('+')

  xpk_print('xpk_version:', xpk_version)
  xpk_print('git commit hash:', git_hash)
