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

from argparse import Namespace
import os

from ..core.commands import run_command_for_value

XPK_VERSION = '0.4.1'

from ..utils.console import xpk_exit, xpk_print


def version(args: Namespace) -> None:
  """Get version of xpk."""
  xpk_version = XPK_VERSION
  if os.path.exists(os.path.join(os.getcwd(), '.git')):
    code, xpk_version = run_command_for_value(
        'git rev-parse HEAD', task='Get latest hash', global_args=args
    )
    if code != 0:
      xpk_exit(code)
    xpk_print('xpk build from sources.')
  xpk_print('xpk version: ', xpk_version.strip('\n'))
