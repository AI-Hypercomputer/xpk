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

import platform
from ..core.config import __version__ as xpk_version


def get_user_agent() -> str:
  return f'XPK/{xpk_version} ({_get_user_agent_platform()})'


def _get_user_agent_platform() -> str:
  system = platform.system().lower()
  if system == 'windows':
    return f'Windows NT {platform.version()}'
  elif system == 'linux':
    return f'Linux; {platform.machine()}'
  elif system == 'darwin':
    version, _, arch = platform.mac_ver()
    return f'Macintosh; {arch} Mac OS X {version}'
  else:
    return ''
