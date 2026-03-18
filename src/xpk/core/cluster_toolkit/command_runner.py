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

from abc import ABC, abstractmethod


class CommandRunner(ABC):
  """This is a base class that defines methods a class for running cluster toolkit command should implement."""

  @abstractmethod
  def initialize(self) -> None:
    """initialize is a method that should implement all steps necessary to run command.

    Returns:
        None
    """
    return None

  @abstractmethod
  def run_command(self, cmd: str) -> None:
    """run_command implements executing command. If command execution fails, exception should be raised.

    Args:
        cmd (str): command to run

    Returns:
        None:
    """
    return None

  @abstractmethod
  def upload_file_to_working_dir(self, path: str, prefix: str = "") -> str:
    """Uploads single file to working directory.

    Args:
        path (str): path to file to upload

    Returns:
        str: path to a destination file
    """
    return ""

  @abstractmethod
  def upload_directory_to_working_dir(self, path: str, prefix: str = "") -> str:
    """upload directory and its content to working directory.

    Args:
        path (str): path pointing to directory that will be uploaded.

    Returns:
        str: path to a target directory.
    """
    return ""
