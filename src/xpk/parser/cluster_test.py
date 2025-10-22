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

import argparse
from xpk.parser.cluster import set_cluster_create_parser
import pytest
from ..utils.feature_flags import FeatureFlags


@pytest.fixture(autouse=True)
def with_sub_slicing_enabled():
  FeatureFlags.SUB_SLICING_ENABLED = True


def test_cluster_create_sub_slicing_is_hidden_with_flag_off():
  FeatureFlags.SUB_SLICING_ENABLED = False
  parser = argparse.ArgumentParser()

  set_cluster_create_parser(parser)
  help_str = parser.format_help()

  assert "--sub-slicing" not in help_str


def test_cluster_create_sub_slicing_is_shown_with_flag_on():
  parser = argparse.ArgumentParser()

  set_cluster_create_parser(parser)
  help_str = parser.format_help()

  assert "--sub-slicing" in help_str


def test_cluster_create_sub_slicing_is_false_by_default():
  parser = argparse.ArgumentParser()

  set_cluster_create_parser(parser)
  args = parser.parse_args(
      ["--cluster", "test-cluster", "--tpu-type", "test-tpu"]
  )

  assert args.sub_slicing is False


def test_cluster_create_sub_slicing_can_be_set():
  parser = argparse.ArgumentParser()

  set_cluster_create_parser(parser)
  args = parser.parse_args(
      ["--cluster", "test-cluster", "--tpu-type", "test-tpu", "--sub-slicing"]
  )

  assert args.sub_slicing is True
