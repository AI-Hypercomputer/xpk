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

from xpk.core.docker_manager import DockerManager
from xpk.core.gcluster import GclusterManager
from xpk.core.blueprint.blueprint_generator import BlueprintGenerator
import pytest
import os
import shutil

ctk_gcloud_cfg = os.getenv("GCLOUD_CFG_PATH")
project_id = os.getenv("PROJECT_ID")
region = os.getenv("REGION")
zone = os.getenv("ZONE")
auth_cidr = os.getenv("AUTH_CIDR")
cluster_name = os.getenv("CLUSTER_NAME")

uploads_dir = "uploads"


def prepare_test(docker_path: str, bp_path: str) -> None:
  os.mkdir(docker_path)
  os.mkdir(bp_path)


@pytest.mark.skip(
    reason=(
        "This test requires A3 capacity, therefore it should not be run on each"
        " build. Please invoke it manually if needed. "
    )
)
def test_create_a3_mega_deployment():
  assert project_id is not None
  assert region is not None
  assert zone is not None
  assert auth_cidr is not None
  assert ctk_gcloud_cfg is not None
  assert cluster_name is not None

  pwd = os.getcwd()
  test_docker_working_dir = os.path.join(pwd, "xpk_test_docker_dir")
  test_bp_dir = os.path.join(pwd, "xpk_test_bp_dir")
  prepare_test(test_docker_working_dir, test_bp_dir)
  blueprint_name = f"{cluster_name}-a3-mega-xpk"

  docker_manager = DockerManager(
      gcloud_cfg_path=ctk_gcloud_cfg, working_dir=test_docker_working_dir
  )
  docker_manager.initialize()

  bpm = BlueprintGenerator(storage_path=test_bp_dir)
  a3_mega_blueprint = bpm.generate_a3_ultra_blueprint(
      cluster_name=cluster_name,
      blueprint_name=blueprint_name,
      region=region,
      project_id=project_id,
      auth_cidr=auth_cidr,
      zone=zone,
  )
  blueprint_test_path = os.path.join(test_bp_dir, f"{blueprint_name}.yaml")
  blueprint_deps_test_path = os.path.join(test_bp_dir, blueprint_name)

  assert a3_mega_blueprint.blueprint_file == blueprint_test_path
  assert a3_mega_blueprint.blueprint_dependencies == blueprint_deps_test_path

  assert os.path.isfile(blueprint_test_path)
  assert os.path.isdir(blueprint_deps_test_path)
  assert os.path.isfile(
      os.path.join(blueprint_deps_test_path, "config-map.yaml.tftpl")
  )
  assert os.path.isfile(
      os.path.join(
          blueprint_deps_test_path, "kueue-xpk-configuration.yaml.tftpl"
      )
  )
  gcluster_manager = GclusterManager(
      gcluster_command_runner=docker_manager,
  )

  staged_bp_path = gcluster_manager.stage_files(
      blueprint_file=a3_mega_blueprint.blueprint_file,
      blueprint_dependencies=a3_mega_blueprint.blueprint_dependencies,
  )

  assert staged_bp_path == os.path.join(
      test_docker_working_dir, uploads_dir, f"{blueprint_name}.yaml"
  )
  staged_bp_deps_path = os.path.join(
      test_docker_working_dir, uploads_dir, blueprint_name
  )

  assert os.path.isfile(staged_bp_path)
  assert os.path.isdir(staged_bp_deps_path)
  assert os.path.isfile(
      os.path.join(staged_bp_deps_path, "config-map.yaml.tftpl")
  )
  assert os.path.isfile(
      os.path.join(staged_bp_deps_path, "kueue-xpk-configuration.yaml.tftpl")
  )
  print(staged_bp_path, blueprint_name)
  gcluster_manager.deploy(
      blueprint_path=staged_bp_path, deployment_name=blueprint_name
  )

  #   cleanup part
  gcluster_manager.destroy_deployment(deployment_name=blueprint_name)
  shutil.rmtree(test_docker_working_dir)
  shutil.rmtree(test_bp_dir)
