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

from xpk.utils.console import xpk_print
from ..commands.config import xpk_cfg
from ..core.config import DEPENDENCIES_KEY

validation_commands = {
  'kubectl': {
    'command': 'kubectl --help',
    'message': 'foo'
  },
  'kjob': {
    'command': 'kubectl kjob --help',
    'message': 'foo'
  },
  'gcloud': {
    'command': 'gcloud version',
    'message': 'foo'
  },
  'docker': {
    'command': 'docker version',
    'message': 'foo'
  },
  'kueuectl': {
    'command': 'kubectl kueue',
    'message': 'foo'
  }
}

def validate_dependecies():
  if xpk_cfg.get(DEPENDENCIES_KEY) is None:
    pass
