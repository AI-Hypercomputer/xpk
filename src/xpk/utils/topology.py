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


def is_topology_valid(topology: str) -> bool:
  try:
    parse_topology(topology)
    return True
  except ValueError:
    return False


def get_topology_product(topology: str) -> int:
  return reduce(mul, parse_topology(topology), 1)


def parse_topology(topology: str) -> list[int]:
  if len(topology) <= 0:
    raise ValueError("Topology is an empty string")

  return [int(el) for el in topology.lower().split("x")]


def is_topology_contained(contained: str, container: str) -> bool:
  contained_parsed = parse_topology(contained)
  container_parsed = parse_topology(container)
  return len(contained_parsed) == len(container_parsed) and all(
      contained <= container
      for contained, container in zip(contained_parsed, container_parsed)
  )


def get_slice_topology_level(topology: str) -> str:
  return f"cloud.google.com/gke-tpu-slice-{topology}-id"
