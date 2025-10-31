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

import pytest
from .topology import is_topology_valid, get_topology_product, parse_topology, is_topology_contained


def test_is_topology_valid_with_invalid_topology():
  result = is_topology_valid("N/A")
  assert result is False


def test_is_topology_valid_with_valid_topology():
  result = is_topology_valid("1x1x1")
  assert result is True


def test_parse_topology_with_valid_topology():
  result = parse_topology("1x2x3")
  assert result == [1, 2, 3]


def test_parse_topology_with_empty_input():
  with pytest.raises(ValueError):
    parse_topology("")


def test_get_topology_product():
  result = get_topology_product("1x2x3")
  assert result == 6


def test_is_topology_contained_with_container_smaller_than_contained_returns_false():
  result = is_topology_contained(contained="3x3x3", container="2x2x2")
  assert result is False


def test_is_topology_contained_with_container_larger_than_contained_returns_true():
  result = is_topology_contained(contained="1x1x1", container="2x2x2")
  assert result is True


def test_is_topology_contained_with_container_equal_to_contained_returns_true():
  result = is_topology_contained(contained="2x2x2", container="2x2x2")
  assert result is True


def test_is_topology_contained_with_different_topologies_dimensions_returns_false():
  result = is_topology_contained(contained="2x2", container="2x2x2")
  assert result is False
