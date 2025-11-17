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

from xpk.commands.cluster_gcluster import get_unique_name
from xpk.core.docker_manager import DockerManager
from xpk.core.gcluster_manager import GclusterManager
from xpk.core.blueprint.blueprint_generator import BlueprintGenerator
from xpk.utils.versions import ReleaseChannel
import pytest
import os
import shutil

ctk_gcloud_cfg = os.getenv("GCLOUD_CFG_PATH")
project_id = os.getenv("PROJECT_ID")
region = os.getenv("REGION")
zone = os.getenv("ZONE")
auth_cidr = os.getenv("AUTH_CIDR")
cluster_name = os.getenv("A3_MEGA_TEST_CLUSTER_NAME")
release_channel = os.getenv("RELEASE_CHANNEL")
cluster_version = os.getenv("CLUSTER_VERSION")

uploads_dir = "uploads"


@pytest.fixture(name="setup_tests")
def prepare_test():
  pwd = os.getcwd()
  docker_path = os.path.join(pwd, "xpk_test_docker_dir")
  bp_path = os.path.join(pwd, "xpk_bp_path")
  if not os.path.exists(docker_path):
    os.makedirs(docker_path)
  if not os.path.exists(bp_path):
    os.makedirs(bp_path)
  yield (docker_path, bp_path)
  shutil.rmtree(docker_path)
  shutil.rmtree(bp_path)


@pytest.mark.skip(
    reason=(
        "This test requires A3 capacity, therefore it should not be run on each"
        " build. Please invoke it manually if needed. "
    )
)
def test_deploy_a3_mega_deployment(setup_tests):
  docker_path, bp_path = setup_tests[0], setup_tests[1]
  (
      blueprint_name,
      prefix,
      gcluster_manager,
      staged_bp_path,
  ) = create_test_a3_mega_deployment(docker_path, bp_path)
  gcluster_manager.deploy(
      blueprint_path=staged_bp_path,
      deployment_name=blueprint_name,
      prefix=prefix,
  )

  #   cleanup part
  gcluster_manager.destroy_deployment(
      deployment_name=blueprint_name, prefix=prefix
  )
  shutil.rmtree(docker_path)
  shutil.rmtree(bp_path)


@pytest.mark.skip(
    reason=(
        "This test requires A3 capacity, therefore it should not be run on each"
        " build. Please invoke it manually if needed. "
    )
)
def test_create_a3_mega_deployment_files(setup_tests):
  assert project_id is not None
  assert region is not None
  assert zone is not None
  assert auth_cidr is not None
  assert ctk_gcloud_cfg is not None
  assert cluster_name is not None
  assert release_channel is not None
  assert cluster_version is not None
  docker_path, bp_path = setup_tests[0], setup_tests[1]

  blueprint_name = f"{cluster_name}-a3-mega-xpk"
  prefix = "prefix"

  docker_manager = DockerManager(
      gcloud_cfg_path=ctk_gcloud_cfg, working_dir=docker_path
  )
  docker_manager.initialize()

  bpm = BlueprintGenerator(storage_path=bp_path)
  a3_mega_blueprint = bpm.generate_a3_mega_blueprint(
      cluster_name=cluster_name,
      blueprint_name=blueprint_name,
      prefix=prefix,
      region=region,
      project_id=project_id,
      auth_cidr=auth_cidr,
      zone=zone,
      system_node_pool_min_node_count=3,
      release_channel=ReleaseChannel(release_channel),
      cluster_version=cluster_version,
  )
  blueprint_test_path = os.path.join(bp_path, prefix, f"{blueprint_name}.yaml")
  blueprint_deps_test_path = os.path.join(bp_path, prefix, blueprint_name)

  assert a3_mega_blueprint.blueprint_file == blueprint_test_path
  assert a3_mega_blueprint.blueprint_dependencies == blueprint_deps_test_path

  assert os.path.isfile(blueprint_test_path)
  assert os.path.isdir(blueprint_deps_test_path)
  assert os.path.isfile(
      os.path.join(blueprint_deps_test_path, "config-map.yaml.tftpl")
  )

  gcluster_manager = GclusterManager(
      gcluster_command_runner=docker_manager, remote_state_client=None
  )

  staged_bp_path = gcluster_manager.stage_files(
      blueprint_file=a3_mega_blueprint.blueprint_file,
      blueprint_dependencies=a3_mega_blueprint.blueprint_dependencies,
      prefix=prefix,
  )

  assert staged_bp_path == os.path.join(
      "/out", uploads_dir, prefix, f"{blueprint_name}.yaml"
  )

  staged_bp_path_local = os.path.join(
      docker_path, uploads_dir, prefix, f"{blueprint_name}.yaml"
  )
  staged_bp_deps_path_local = os.path.join(
      docker_path, uploads_dir, prefix, blueprint_name
  )

  assert os.path.isfile(staged_bp_path_local)
  assert os.path.isdir(staged_bp_deps_path_local)
  assert os.path.isfile(
      os.path.join(staged_bp_deps_path_local, "config-map.yaml.tftpl")
  )
  assert os.path.isfile(
      os.path.join(
          staged_bp_deps_path_local, "kueue-xpk-configuration.yaml.tftpl"
      )
  )
  unique_name = get_unique_name(project_id, region, zone)
  gcluster_manager.deploy(
      blueprint_path=staged_bp_path, deployment_name=unique_name, dry_run=True
  )


def create_test_a3_mega_deployment(docker_path: str, bp_path: str):
  assert project_id is not None
  assert region is not None
  assert zone is not None
  assert auth_cidr is not None
  assert ctk_gcloud_cfg is not None
  assert cluster_name is not None
  assert release_channel is not None
  assert cluster_version is not None

  blueprint_name = f"{cluster_name}-a3-mega-xpk"
  prefix = "prefix"

  docker_manager = DockerManager(
      gcloud_cfg_path=ctk_gcloud_cfg, working_dir=docker_path
  )
  docker_manager.initialize()

  bpm = BlueprintGenerator(storage_path=bp_path)
  a3_mega_blueprint = bpm.generate_a3_mega_blueprint(
      cluster_name=cluster_name,
      blueprint_name=blueprint_name,
      prefix=prefix,
      region=region,
      project_id=project_id,
      auth_cidr=auth_cidr,
      zone=zone,
      system_node_pool_min_node_count=3,
      release_channel=ReleaseChannel(release_channel),
      cluster_version=cluster_version,
  )

  gcluster_manager = GclusterManager(
      gcluster_command_runner=docker_manager,
      remote_state_client=None,
  )

  staged_bp_path = gcluster_manager.stage_files(
      blueprint_file=a3_mega_blueprint.blueprint_file,
      blueprint_dependencies=a3_mega_blueprint.blueprint_dependencies,
      prefix=prefix,
  )

  return (
      blueprint_name,
      prefix,
      gcluster_manager,
      staged_bp_path,
  )
