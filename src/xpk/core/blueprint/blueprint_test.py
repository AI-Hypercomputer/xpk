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

import os
import shutil

import ruamel.yaml

from xpk.core.blueprint.blueprint_definitions import Blueprint
from xpk.core.blueprint.blueprint_generator import BlueprintGenerator
from xpk.core.capacity import CapacityType
from xpk.utils.versions import ReleaseChannel

yaml = ruamel.yaml.YAML()

yaml.register_class(Blueprint)

a3_yaml_test_path = "src/xpk/core/blueprint/testing/data/a3_mega.yaml"
a3_spot_yaml_test_path = "src/xpk/core/blueprint/testing/data/a3_mega_spot.yaml"
a3_ultra_yaml_test_path = "src/xpk/core/blueprint/testing/data/a3_ultra.yaml"
a4_yaml_test_path = "src/xpk/core/blueprint/testing/data/a4.yaml"
config_map_filename = "config-map.yaml.tftpl"
tmp_test_dir = "/tmp/xpk_test"


def prepare_test():
  if os.path.exists(tmp_test_dir):
    shutil.rmtree(tmp_test_dir)
  os.mkdir(tmp_test_dir)


def test_generate_a3_mega_blueprint():
  prepare_test()
  blueprint_name = "xpk-gke-a3-megagpu"
  bp_generator = BlueprintGenerator(tmp_test_dir)
  bp = bp_generator.generate_a3_mega_blueprint(
      project_id="foo",
      cluster_name="bar",
      blueprint_name=blueprint_name,
      prefix="prefix",
      region="us-central1",
      zone="us-central1-c",
      auth_cidr="10.0.0.0/32",
      reservation_placement_policy={
          "type": "COMPACT",
          "name": "test-reservation-placement",
      },
      reservation="test-reservation",
      capacity_type=CapacityType.RESERVATION,
      system_node_pool_min_node_count=5,
      release_channel=ReleaseChannel.RAPID,
      cluster_version="1.2.3",
  )

  assert bp.blueprint_file.endswith("/prefix/xpk-gke-a3-megagpu.yaml")

  with open(a3_yaml_test_path, encoding="utf-8") as stream:
    ctk_yaml = yaml.load(stream)
    with open(bp.blueprint_file, encoding="utf-8") as generated_blueprint:
      ctk_test = yaml.load(generated_blueprint)
      assert ctk_yaml.blueprint_name == ctk_test.blueprint_name
      assert ctk_test.terraform_backend_defaults is None
      assert ctk_yaml.toolkit_modules_url == ctk_test.toolkit_modules_url
      assert (
          ctk_yaml.toolkit_modules_version == ctk_test.toolkit_modules_version
      )
      assert ctk_yaml.vars == ctk_test.vars
      assert ctk_test.deployment_groups == ctk_yaml.deployment_groups
      assert os.path.exists(
          os.path.join(
              tmp_test_dir, "prefix", blueprint_name, config_map_filename
          )
      )

  shutil.rmtree(tmp_test_dir)


def test_generate_a3_mega_spot_blueprint():
  prepare_test()
  blueprint_name = "xpk-gke-a3-megagpu"
  bp_generator = BlueprintGenerator(tmp_test_dir)
  bp = bp_generator.generate_a3_mega_blueprint(
      project_id="foo",
      cluster_name="bar",
      blueprint_name=blueprint_name,
      prefix="prefix",
      region="us-central1",
      zone="us-central1-c",
      auth_cidr="10.0.0.0/32",
      capacity_type=CapacityType.SPOT,
      system_node_pool_min_node_count=5,
      release_channel=ReleaseChannel.RAPID,
      cluster_version="1.2.3",
  )

  assert bp.blueprint_file.endswith("/prefix/xpk-gke-a3-megagpu.yaml")

  with open(a3_spot_yaml_test_path, encoding="utf-8") as stream:
    ctk_yaml = yaml.load(stream)
    with open(bp.blueprint_file, encoding="utf-8") as generated_blueprint:
      ctk_test = yaml.load(generated_blueprint)
      assert ctk_yaml.blueprint_name == ctk_test.blueprint_name
      assert ctk_test.terraform_backend_defaults is None
      assert ctk_yaml.toolkit_modules_url == ctk_test.toolkit_modules_url
      assert (
          ctk_yaml.toolkit_modules_version == ctk_test.toolkit_modules_version
      )
      assert ctk_yaml.vars == ctk_test.vars
      assert ctk_test.deployment_groups == ctk_yaml.deployment_groups

  shutil.rmtree(tmp_test_dir)


def test_generate_a3_ultra_blueprint():
  prepare_test()
  blueprint_name = "xpk-gke-a3-ultra"
  bp_generator = BlueprintGenerator(tmp_test_dir)
  bp = bp_generator.generate_a3_ultra_blueprint(
      project_id="foo",
      cluster_name="gke-a3-ultra",
      blueprint_name=blueprint_name,
      region="us-central1",
      zone="us-central1-c",
      auth_cidr="10.0.0.0/32",
      reservation="test-reservation",
      system_node_pool_machine_type="e2-standard-16",
      capacity_type=CapacityType.RESERVATION,
      gcs_bucket="test-bucket",
      prefix="testdir",
      release_channel=ReleaseChannel.RAPID,
      cluster_version="1.2.3",
  )
  with open(a3_ultra_yaml_test_path, encoding="utf-8") as stream:
    ctk_yaml = yaml.load(stream)
    with open(bp.blueprint_file, encoding="utf-8") as generated_blueprint:
      ctk_test = yaml.load(generated_blueprint)
      assert ctk_yaml.blueprint_name == ctk_test.blueprint_name
      assert (
          ctk_yaml.terraform_backend_defaults
          == ctk_test.terraform_backend_defaults
      )
      assert ctk_yaml.toolkit_modules_url == ctk_test.toolkit_modules_url
      assert (
          ctk_yaml.toolkit_modules_version == ctk_test.toolkit_modules_version
      )
      assert ctk_test.deployment_groups == ctk_yaml.deployment_groups
      assert os.path.exists(
          os.path.join(
              tmp_test_dir, "testdir", blueprint_name, "mlgru-disable.yaml"
          )
      )
      assert os.path.exists(
          os.path.join(
              tmp_test_dir, "testdir", blueprint_name, "nccl-installer.yaml"
          )
      )

  shutil.rmtree(tmp_test_dir)


def test_generate_a4_blueprint():
  prepare_test()
  blueprint_name = "xpk-gke-a4"
  bp_generator = BlueprintGenerator(tmp_test_dir)
  bp = bp_generator.generate_a4_blueprint(
      project_id="foo",
      cluster_name="gke-a4",
      blueprint_name=blueprint_name,
      region="us-central1",
      zone="us-central1-c",
      auth_cidr="10.0.0.0/32",
      reservation="test-reservation",
      system_node_pool_machine_type="e2-standard-16",
      capacity_type=CapacityType.RESERVATION,
      gcs_bucket="test-bucket",
      prefix="testdir",
      release_channel=ReleaseChannel.RAPID,
      cluster_version="1.2.3",
  )
  with open(a4_yaml_test_path, encoding="utf-8") as stream:
    ctk_yaml = yaml.load(stream)
    with open(bp.blueprint_file, encoding="utf-8") as generated_blueprint:
      ctk_test = yaml.load(generated_blueprint)
      assert ctk_yaml.blueprint_name == ctk_test.blueprint_name
      assert (
          ctk_yaml.terraform_backend_defaults
          == ctk_test.terraform_backend_defaults
      )
      assert ctk_yaml.toolkit_modules_url == ctk_test.toolkit_modules_url
      assert (
          ctk_yaml.toolkit_modules_version == ctk_test.toolkit_modules_version
      )
      assert ctk_test.deployment_groups == ctk_yaml.deployment_groups
      assert os.path.exists(
          os.path.join(
              tmp_test_dir, "testdir", blueprint_name, "storage_crd.yaml"
          )
      )
      assert os.path.exists(
          os.path.join(
              tmp_test_dir,
              "testdir",
              blueprint_name,
              "nccl-rdma-installer-a4.yaml",
          )
      )

  shutil.rmtree(tmp_test_dir)
