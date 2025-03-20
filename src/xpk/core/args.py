"""
Copyright 2024 Google LLC

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

import inspect
from argparse import Namespace
from typing import Any, Optional


class GlobalConfig:
  """Class representing global args type"""

  dry_run: bool = False


class SlurmConfig:
  """Class representing slurm args type"""

  ignore_unknown_flags: bool = False
  array: Optional[str] = None
  cpus_per_task: Optional[str] = None
  gpus_per_task: Optional[str] = None
  mem: Optional[str] = None
  mem_per_task: Optional[str] = None
  mem_per_cpu: Optional[str] = None
  mem_per_gpu: Optional[str] = None
  nodes: Optional[int] = None
  ntasks: Optional[int] = None
  output: Optional[str] = None
  error: Optional[str] = None
  input: Optional[str] = None
  job_name: Optional[str] = None
  chdir: Optional[str] = None
  time: Optional[str] = None


def apply_args(main_args: Namespace, annotation: Any) -> Any:
  args = annotation()

  # getters and setters
  for param in inspect.get_annotations(annotation):
    if param in main_args:
      setattr(args, param, getattr(main_args, param))

  # parameters
  for param, _ in inspect.getmembers(annotation):
    if param in main_args:
      setattr(args, param, getattr(main_args, param))

  return args  # pytype: disable=bad-return-type
