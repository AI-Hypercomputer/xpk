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
from xpk.parser.cluster import set_cluster_create_parser, set_cluster_create_pathways_parser, set_cluster_create_ray_parser
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
      ["--cluster", "test-cluster", "--tpu-type", "tpu7x-2"]
  )

  assert args.sub_slicing is False


def test_cluster_create_sub_slicing_can_be_set():
  parser = argparse.ArgumentParser()

  set_cluster_create_parser(parser)
  args = parser.parse_args(
      ["--cluster", "test-cluster", "--tpu-type", "tpu7x-2", "--sub-slicing"]
  )

  assert args.sub_slicing is True


def test_cluster_create_pathways_sub_slicing_is_hidden_with_flag_off():
  FeatureFlags.SUB_SLICING_ENABLED = False
  parser = argparse.ArgumentParser()

  set_cluster_create_pathways_parser(parser)
  help_str = parser.format_help()

  assert "--sub-slicing" not in help_str


def test_cluster_create_pathways_sub_slicing_can_be_set():
  parser = argparse.ArgumentParser()

  set_cluster_create_pathways_parser(parser)
  args = parser.parse_args(
      ["--cluster", "test-cluster", "--tpu-type", "tpu7x-2", "--sub-slicing"]
  )

  assert args.sub_slicing is True


def test_cluster_create_ray_sub_slicing_is_hidden_but_set_to_false():
  parser = argparse.ArgumentParser()

  set_cluster_create_ray_parser(parser)
  args = parser.parse_args([
      "--cluster",
      "test-cluster",
      "--tpu-type",
      "tpu7x-2",
      "--ray-version",
      "19.32.0",
  ])
  help_str = parser.format_help()

  assert args.sub_slicing is False
  assert "--sub-slicing" not in help_str


def test_cluster_create_managed_mldiagnostics():
  parser = argparse.ArgumentParser()

  set_cluster_create_parser(parser)
  args = parser.parse_args([
      "--cluster",
      "test-cluster",
      "--tpu-type",
      "v5p-8",
      "--managed-mldiagnostics",
  ])

  assert args.managed_mldiagnostics is True


def test_cluster_create_enable_lustre_legacy_port_is_false_by_default():
  parser = argparse.ArgumentParser()

  set_cluster_create_parser(parser)
  args = parser.parse_args(
      ["--cluster", "test-cluster", "--tpu-type", "tpu7x-2"]
  )

  assert args.enable_legacy_lustre_port is False


def test_cluster_create_enable_lustre_legacy_port_can_be_set():
  parser = argparse.ArgumentParser()

  set_cluster_create_parser(parser)
  args = parser.parse_args([
      "--cluster",
      "test-cluster",
      "--tpu-type",
      "tpu7x-2",
      "--enable-legacy-lustre-port",
  ])

  assert args.enable_legacy_lustre_port is True


def test_cluster_create_super_slicing_is_hidden_with_flag_off():
  FeatureFlags.SUPER_SLICING_ENABLED = False
  parser = argparse.ArgumentParser()

  set_cluster_create_parser(parser)
  help_str = parser.format_help()

  assert "--super-slicing" not in help_str


def test_cluster_create_super_slicing_is_shown_with_flag_on():
  FeatureFlags.SUPER_SLICING_ENABLED = True
  parser = argparse.ArgumentParser()

  set_cluster_create_parser(parser)
  help_str = parser.format_help()

  assert "--super-slicing" in help_str


def test_cluster_create_super_slicing_is_false_by_default():
  FeatureFlags.SUPER_SLICING_ENABLED = True
  parser = argparse.ArgumentParser()

  set_cluster_create_parser(parser)
  args = parser.parse_args(
      ["--cluster", "test-cluster", "--tpu-type", "tpu7x-2"]
  )

  assert args.super_slicing is False


def test_cluster_create_super_slicing_can_be_set():
  FeatureFlags.SUPER_SLICING_ENABLED = True
  parser = argparse.ArgumentParser()

  set_cluster_create_parser(parser)
  args = parser.parse_args(
      ["--cluster", "test-cluster", "--tpu-type", "tpu7x-2", "--super-slicing"],
  )

  assert args.super_slicing is True


def test_cluster_create_num_cubes_is_hidden_with_flag_off():
  FeatureFlags.SUPER_SLICING_ENABLED = False
  parser = argparse.ArgumentParser()

  set_cluster_create_parser(parser)
  help_str = parser.format_help()

  assert "--num-cubes" not in help_str


def test_cluster_create_num_cubes_is_shown_with_flag_on():
  FeatureFlags.SUPER_SLICING_ENABLED = True
  parser = argparse.ArgumentParser()

  set_cluster_create_parser(parser)
  help_str = parser.format_help()

  assert "--num-cubes" in help_str


def test_cluster_create_num_cubes_can_be_set():
  FeatureFlags.SUPER_SLICING_ENABLED = True
  parser = argparse.ArgumentParser()

  set_cluster_create_parser(parser)
  args = parser.parse_args(
      [
          "--cluster",
          "test-cluster",
          "--tpu-type",
          "tpu7x-2",
          "--num-cubes",
          "5",
      ],
  )

  assert args.num_cubes == 5


def test_cluster_create_num_slices_defaults_to_1_if_no_superslicing_feature():
  FeatureFlags.SUPER_SLICING_ENABLED = False
  parser = argparse.ArgumentParser()

  set_cluster_create_parser(parser)
  args = parser.parse_args(
      [
          "--cluster",
          "test-cluster",
          "--tpu-type",
          "tpu7x-2",
      ],
  )

  assert args.num_slices == 1


def test_cluster_create_num_slices_has_no_default_if_superslicing_feature():
  FeatureFlags.SUPER_SLICING_ENABLED = True
  parser = argparse.ArgumentParser()

  set_cluster_create_parser(parser)
  args = parser.parse_args(
      [
          "--cluster",
          "test-cluster",
          "--tpu-type",
          "tpu7x-2",
      ],
  )

  assert args.num_slices is None
