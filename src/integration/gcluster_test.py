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
from xpk.core.gcluster_manager import GclusterManager
from xpk.core.blueprint.blueprint_generator import BlueprintGenerator
import os
import pytest
import shutil

ctk_gcloud_cfg = os.getenv("GCLOUD_CFG_PATH")
project_id = os.getenv("PROJECT_ID")
region = os.getenv("REGION")
zone = os.getenv("ZONE")
auth_cidr = os.getenv("AUTH_CIDR")
cluster_name = os.getenv("GKE_ML_TEST_CLUSTER_NAME")

uploads_dir = "uploads"


def prepare_test(docker_path: str, bp_path: str) -> None:
  if not os.path.exists(docker_path):
    os.makedirs(docker_path)
  if not os.path.exists(bp_path):
    os.makedirs(bp_path)


@pytest.mark.skip(reason="Credentails not working. Skipping for now")
def test_create_deployment():
  assert project_id is not None
  assert region is not None
  assert zone is not None
  assert auth_cidr is not None
  assert ctk_gcloud_cfg is not None
  assert cluster_name is not None

  pwd = os.getcwd()
  test_docker_working_dir = os.path.join(
      pwd, "xpkclusters/tests/xpk_test_docker_dir"
  )
  test_bp_dir = os.path.join(pwd, "xpkclusters/tests/xpk_test_bp_dir")
  prepare_test(test_docker_working_dir, test_bp_dir)
  blueprint_name = "my-test-blueprint"
  prefix = "prefix"

  docker_manager = DockerManager(
      gcloud_cfg_path=ctk_gcloud_cfg, working_dir=test_docker_working_dir
  )
  docker_manager.initialize()

  bpm = BlueprintGenerator(storage_path=test_bp_dir)
  ml_gke_blueprint = bpm.generate_gke_ml_blueprint(
      cluster_name=cluster_name,
      blueprint_name=blueprint_name,
      prefix=prefix,
      region=region,
      project_id=project_id,
      auth_cidr=auth_cidr,
  )
  blueprint_test_path = os.path.join(
      test_bp_dir, prefix, f"{blueprint_name}.yaml"
  )
  # there are no files in ghcp stage for this blueprint
  blueprint_deps_test_path = ""

  assert ml_gke_blueprint.blueprint_file == blueprint_test_path
  assert ml_gke_blueprint.blueprint_dependencies == blueprint_deps_test_path

  assert os.path.exists(blueprint_test_path)

  gcluster_manager = GclusterManager(
      gcluster_command_runner=docker_manager, remote_state_client=None
  )

  staged_bp_path = gcluster_manager.stage_files(
      blueprint_file=ml_gke_blueprint.blueprint_file,
      blueprint_dependencies=ml_gke_blueprint.blueprint_dependencies,
      prefix=prefix,
  )

  assert staged_bp_path == os.path.join(
      "/out", uploads_dir, prefix, f"{blueprint_name}.yaml"
  )

  gcluster_manager.deploy(
      blueprint_path=staged_bp_path,
      deployment_name=blueprint_name,
      prefix=prefix,
  )
  gcluster_manager.destroy_deployment(
      deployment_name=blueprint_name, prefix=prefix
  )
  shutil.rmtree(test_docker_working_dir)
  shutil.rmtree(test_bp_dir)
