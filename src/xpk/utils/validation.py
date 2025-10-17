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
from enum import Enum
from dataclasses import dataclass


@dataclass
class _SystemDependency:
  command: str
  message: str


class SystemDependency(Enum):
  """Represents required system dependencies."""
  KUBECTL = _SystemDependency(
      command='kubectl --help',
      message=(
          '`kubectl` not installed. Please follow'
          ' https://github.com/AI-Hypercomputer/xpk?tab=readme-ov-file#prerequisites'
          ' to install xpk prerequisites.'
      ),
  )
  KJOB = _SystemDependency(
      command='kubectl kjob --help',
      message=(
          '`kjobctl` not installed. Please follow'
          ' https://github.com/AI-Hypercomputer/xpk?tab=readme-ov-file#prerequisites'
          ' to install xpk prerequisites.'
      ),
  )
  GCLOUD = _SystemDependency(
      command='gcloud version',
      message=(
          '`gcloud not installed. Please follow'
          ' https://github.com/AI-Hypercomputer/xpk?tab=readme-ov-file#prerequisites'
          ' to install xpk prerequisites.'
      ),
  )
  DOCKER = _SystemDependency(
      command='docker version',
      message=(
          '`docker` not installed. Please follow'
          ' https://github.com/AI-Hypercomputer/xpk?tab=readme-ov-file#prerequisites'
          ' to install xpk prerequisites.'
      ),
  )
  KUEUECTL = _SystemDependency(
      command='kubectl kueue --help',
      message=(
          '`kueuectl` not installed. Please follow'
          ' https://github.com/AI-Hypercomputer/xpk?tab=readme-ov-file#prerequisites'
          ' to install xpk prerequisites.'
      ),
  )


def validate_dependencies():
  """Validates all system dependencies if validation has not been done with current XPK version."""
  deps_version = xpk_cfg.get(DEPENDENCIES_KEY)
  xpk_version = get_xpk_version()
  if deps_version is None or deps_version != xpk_version:
    for dependency in SystemDependency:
      validate_dependency(dependency)
    xpk_cfg.set(DEPENDENCIES_KEY, get_xpk_version())


def validate_dependency(dependency: SystemDependency) -> None:
  """Validates system dependency and returns none or exits with error."""
  name, value = dependency.name, dependency.value
  cmd, message = value.command, value.message
  code, _ = run_command_for_value(cmd, f'Validate {name} installation.')
  if code != 0:
    xpk_print(message)
    xpk_exit(code)
