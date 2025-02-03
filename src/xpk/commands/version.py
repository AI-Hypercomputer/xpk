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

from ..core.core import __git_commit_hash__
from ..utils.console import xpk_print

XPK_VERSION = 'v0.6.0'


def version() -> None:
  """Get version of xpk."""
  xpk_print('xpk_version:', XPK_VERSION)
  xpk_print('git commit hash:', __git_commit_hash__)
