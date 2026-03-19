"""
Copyright 2026 Google LLC

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

import os
from shutil import copytree, copy
from ...utils.console import xpk_print, xpk_exit
from ...utils.file import ensure_directory_exists
from ...utils.dependencies.manager import ensure_dependency
from ...utils.dependencies.binary_dependencies import BinaryDependencies
from ..commands import run_command_with_full_controls
from .command_runner import CommandRunner


class NativeCommandRunner(CommandRunner):
  """NativeCommandRunner is a class for managing gcluster execution natively.
  Attributes:
    - working_dir (str) : path to directory in which gcluster deployment directory will be saved
  """

  def __init__(self, working_dir: str) -> None:
    self.working_dir = working_dir

  def initialize(self) -> None:
    """Initialize native command runner by ensuring gcluster binary is downloaded."""
    xpk_print("Initializing native command runner...")
    if not ensure_dependency(BinaryDependencies.GCLUSTER.value):
      xpk_print("Failed to ensure gcluster dependency.")
      xpk_exit(1)
    xpk_print("gcluster dependency ensured.")

  def run_command(self, cmd: str) -> None:
    """Run gcluster command natively on the host machine."""
    return_code = run_command_with_full_controls(
        command=cmd,
        task="gcluster execution",
    )
    if return_code != 0:
      xpk_print(
          f"Running gcluster command: {cmd} failed with code {return_code}."
      )
      xpk_exit(return_code)

  def _get_upload_directory(self, prefix: str = "") -> str:
    upload_dir = os.path.join(self.working_dir, "uploads", prefix)
    ensure_directory_exists(upload_dir)
    return upload_dir

  def get_deployment_dir(self, prefix: str = "") -> str:
    prefix = f"/{prefix}" if prefix != "" else ""
    return f"{self.working_dir}{prefix}"

  def upload_directory_to_working_dir(self, path: str, prefix: str = "") -> str:
    """Move file or directory from specified path to directory containing deployment files

    Args:
        path (str): path of directory/file that will be moved to deployment directory
    """
    name = path.split("/")[-1]
    target_path = os.path.join(self._get_upload_directory(prefix), name)
    xpk_print(f"Copying directory from {path} to {target_path}.")
    copytree(path, target_path, dirs_exist_ok=True)
    return target_path

  def upload_file_to_working_dir(self, path: str, prefix: str = "") -> str:
    """Move file or directory from specified path to directory containing deployment files

    Args:
        path (str): path of directory/file that will be moved to deployment directory
    """
    name = path.split("/")[-1]
    target_path = os.path.join(self._get_upload_directory(prefix), name)
    xpk_print(f"Copying a file from {path} to {target_path}.")
    copy(path, target_path)
    return target_path
