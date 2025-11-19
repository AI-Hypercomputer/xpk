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

import pytest

from xpk.commands.cluster_gcluster import get_unique_name
from xpk.core.blueprint.blueprint_generator import BlueprintGenerator
from xpk.core.capacity import CapacityType
from xpk.core.docker_manager import DockerManager
from xpk.core.gcluster_manager import GclusterManager
from xpk.utils.versions import ReleaseChannel

ctk_gcloud_cfg = os.getenv("GCLOUD_CFG_PATH")
project_id = os.getenv("PROJECT_ID")
region = os.getenv("REGION")
zone = os.getenv("ZONE")
auth_cidr = os.getenv("AUTH_CIDR")
cluster_name = os.getenv("A4_TEST_CLUSTER_NAME")
release_channel = os.getenv("RELEASE_CHANNEL")
cluster_version = os.getenv("CLUSTER_VERSION")


@pytest.fixture(name="setup_tests")
def prepare_test():
  pwd = os.getcwd()
  docker_path = os.path.join(pwd, "xpk_test_docker_dir")
  bp_path = os.path.join(pwd, "xpk_test_bp_dir")
  if not os.path.exists(docker_path):
    os.makedirs(docker_path)
  if not os.path.exists(bp_path):
    os.makedirs(bp_path)
  yield (docker_path, bp_path)
  shutil.rmtree(docker_path)
  shutil.rmtree(bp_path)


@pytest.mark.skip(
    reason=(
        "This test requires A4 capacity, therefore it should not be run on each"
        " build. Please invoke it manually if needed. "
    )
)
def test_create_a4_deployment_files(setup_tests):
  assert project_id is not None
  assert region is not None
  assert zone is not None
  assert auth_cidr is not None
  assert ctk_gcloud_cfg is not None
  assert cluster_name is not None
  assert release_channel is not None
  assert cluster_version is not None
  docker_path, bp_path = setup_tests[0], setup_tests[1]
  blueprint_name = f"{cluster_name}-a4-xpk"

  docker_manager = DockerManager(
      gcloud_cfg_path=ctk_gcloud_cfg, working_dir=docker_path
  )
  docker_manager.initialize()
  prefix = f"{project_id}-{region}".lower()
  bpm = BlueprintGenerator(storage_path=bp_path)
  a4_blueprint = bpm.generate_a4_blueprint(
      cluster_name=cluster_name,
      blueprint_name=blueprint_name,
      region=region,
      project_id=project_id,
      auth_cidr=auth_cidr,
      zone=zone,
      reservation="foo",
      num_nodes=1,
      system_node_pool_machine_type="e2-standard-16",
      prefix=prefix,
      release_channel=ReleaseChannel(release_channel),
      cluster_version=cluster_version,
  )
  blueprint_test_path = os.path.join(bp_path, prefix, f"{blueprint_name}.yaml")
  blueprint_deps_test_path = os.path.join(bp_path, blueprint_name)
  assert a4_blueprint.blueprint_file == blueprint_test_path
  assert a4_blueprint.blueprint_dependencies == blueprint_deps_test_path

  assert os.path.isfile(blueprint_test_path)
  assert os.path.isdir(blueprint_deps_test_path)
  assert os.path.isfile(
      os.path.join(blueprint_deps_test_path, "mlgru-disable.yaml")
  )
  assert os.path.isfile(
      os.path.join(blueprint_deps_test_path, "nccl-installer.yaml")
  )
  gcluster_manager = GclusterManager(
      gcluster_command_runner=docker_manager, remote_state_client=None
  )

  staged_bp_path = gcluster_manager.stage_files(
      blueprint_file=a4_blueprint.blueprint_file,
      blueprint_dependencies=a4_blueprint.blueprint_dependencies,
      prefix=prefix,
  )
  assert staged_bp_path == os.path.join(
      "/out/uploads", prefix, f"{blueprint_name}.yaml"
  )
  unique_name = get_unique_name(project_id, region, zone)
  gcluster_manager.deploy(
      blueprint_path=staged_bp_path, deployment_name=unique_name, dry_run=True
  )


@pytest.mark.skip(
    reason=(
        "This test requires A4 capacity, therefore it should not be run on each"
        " build. Please invoke it manually if needed. "
    )
)
def test_create_a4_deployment(setup_tests):
  assert project_id is not None
  assert region is not None
  assert zone is not None
  assert auth_cidr is not None
  assert ctk_gcloud_cfg is not None
  assert cluster_name is not None
  assert release_channel is not None
  assert cluster_version is not None
  docker_path, bp_path = setup_tests[0], setup_tests[1]
  blueprint_name = f"{cluster_name}-a4-xpk"

  docker_manager = DockerManager(
      gcloud_cfg_path=ctk_gcloud_cfg, working_dir=docker_path
  )
  docker_manager.initialize()

  bpm = BlueprintGenerator(storage_path=bp_path)
  a4_blueprint = bpm.generate_a4_blueprint(
      cluster_name=cluster_name,
      blueprint_name=blueprint_name,
      region=region,
      project_id=project_id,
      auth_cidr=auth_cidr,
      zone=zone,
      capacity_type=CapacityType.SPOT,
      num_nodes=1,
      system_node_pool_machine_type="e2-standard-16",
      release_channel=ReleaseChannel(release_channel),
      cluster_version=cluster_version,
  )
  blueprint_test_path = os.path.join(bp_path, f"{blueprint_name}.yaml")
  blueprint_deps_test_path = os.path.join(bp_path, blueprint_name)

  assert a4_blueprint.blueprint_file == blueprint_test_path
  assert a4_blueprint.blueprint_dependencies == blueprint_deps_test_path

  assert os.path.isfile(blueprint_test_path)
  assert os.path.isdir(blueprint_deps_test_path)
  assert os.path.isfile(
      os.path.join(blueprint_deps_test_path, "mlgru-disable.yaml")
  )
  assert os.path.isfile(
      os.path.join(blueprint_deps_test_path, "nccl-installer.yaml")
  )
  gcluster_manager = GclusterManager(
      gcluster_command_runner=docker_manager, remote_state_client=None
  )

  staged_bp_path = gcluster_manager.stage_files(
      blueprint_file=a4_blueprint.blueprint_file,
      blueprint_dependencies=a4_blueprint.blueprint_dependencies,
  )

  gcluster_manager.deploy(
      blueprint_path=staged_bp_path, deployment_name=blueprint_name
  )

  #   cleanup part
  gcluster_manager.destroy_deployment(deployment_name=blueprint_name)
