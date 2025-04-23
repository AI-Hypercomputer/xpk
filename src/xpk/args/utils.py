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
from typing import Any


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
