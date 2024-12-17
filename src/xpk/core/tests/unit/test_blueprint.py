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

import shutil
from xpk.core.blueprint.blueprint_generator import BlueprintGenerator
from xpk.core.blueprint.blueprint_definitions import Blueprint
import ruamel.yaml
import os

yaml = ruamel.yaml.YAML()

yaml.register_class(Blueprint)

a3_yaml_test_path = "src/xpk/core/tests/data/a3_mega.yaml"
config_map_filename = "config-map.yaml.tftpl"
kueue_conf_filename = "kueue-xpk-configuration.yaml.tftpl"
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
      reservation="test-reservation",
      spot=True,
      system_node_pool_min_node_count=5,
  )

  assert bp.blueprint_file.endswith("/prefix/xpk-gke-a3-megagpu.yaml")

  with open(a3_yaml_test_path, encoding="utf-8") as stream:
    ctk_yaml = yaml.load(stream)
    with open(bp.blueprint_file, encoding="utf-8") as generated_blueprint:
      ctk_test = yaml.load(generated_blueprint)
      assert ctk_yaml.blueprint_name == ctk_test.blueprint_name
      assert ctk_yaml.vars == ctk_test.vars
      assert ctk_test.deployment_groups == ctk_yaml.deployment_groups
      assert os.path.exists(
          os.path.join(
              tmp_test_dir, "prefix", blueprint_name, config_map_filename
          )
      )
      assert os.path.exists(
          os.path.join(
              tmp_test_dir, "prefix", blueprint_name, kueue_conf_filename
          )
      )

  shutil.rmtree(tmp_test_dir)
