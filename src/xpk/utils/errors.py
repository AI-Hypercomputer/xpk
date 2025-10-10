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

class CommandExecutionException(Exception):
  command: str
  task: str
  return_code: int

  def __init__(self, command: str, task: str, return_code: int):
    super().__init__()
    self.command = command
    self.task = task
    self.return_code = return_code

  def __str__(self):
    return (
        f"Failed to execute task {self.task}; "
        f"Command: {self.command}; "
        f"Return code: {self.return_code}"
    )
