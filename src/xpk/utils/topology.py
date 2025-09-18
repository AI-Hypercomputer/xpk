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

from functools import reduce
from operator import mul


def is_valid_topology(topology: str) -> bool:
  try:
    get_topology_product(topology)
    return True
  except:
    return False


def get_topology_product(topology: str) -> list[int]:
  parts = [int(x) for x in topology.lower().split('x')]
  return reduce(mul, parts, 1)
