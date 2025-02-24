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

from ..core.commands import run_command_for_value
from .console import xpk_exit, xpk_print
from ..commands.config import xpk_cfg
from ..core.config import DEPENDENCIES_KEY
from ..commands.version import get_xpk_version


validation_commands = {
    'kubectl': {
        'command': 'kubectl --help',
        'message': (
            '`kubectl` not installed. Please follow'
            ' https://github.com/AI-Hypercomputer/xpk?tab=readme-ov-file#prerequisites'
            ' to install xpk prerequisites.'
        ),
    },
    'kjob': {
        'command': 'kubectl kjob --help',
        'message': (
            '`kjobctl` not installed. Please follow'
            ' https://github.com/AI-Hypercomputer/xpk?tab=readme-ov-file#prerequisites'
            ' to install xpk prerequisites.'
        ),
    },
    'gcloud': {
        'command': 'gcloud version',
        'message': (
            '`gcloud not installed. Please follow'
            ' https://github.com/AI-Hypercomputer/xpk?tab=readme-ov-file#prerequisites'
            ' to install xpk prerequisites.'
        ),
    },
    'docker': {
        'command': 'docker version',
        'message': (
            '`docker` not installed. Please follow'
            ' https://github.com/AI-Hypercomputer/xpk?tab=readme-ov-file#prerequisites'
            ' to install xpk prerequisites.'
        ),
    },
    'kueuectl': {
        'command': 'kubectl kueue --help',
        'message': (
            '`kueuectl` not installed. Please follow'
            ' https://github.com/AI-Hypercomputer/xpk?tab=readme-ov-file#prerequisites'
            ' to install xpk prerequisites.'
        ),
    },
}


def validate_dependencies():
  deps_version = xpk_cfg.get(DEPENDENCIES_KEY)
  xpk_version = get_xpk_version()
  if deps_version is None or deps_version != xpk_version:
    for name, check in validation_commands.items():
      cmd, message = check['command'], check['message']
      code, _ = run_command_for_value(
          cmd, f'Validate {name} installation.', None
      )
      if code != 0:
        xpk_print(message)
        xpk_exit(code)
    xpk_cfg.set(DEPENDENCIES_KEY, get_xpk_version())
