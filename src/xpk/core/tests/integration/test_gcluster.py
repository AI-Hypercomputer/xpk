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

from xpk.core.docker_manager import CtkDockerManager
from xpk.core.gcluster import CtkManager
from xpk.core.blueprint import CtkBlueprint, CtkDeploymentGroup, CtkDeploymentModule, create_deployment_directory

import os
import pytest

ctk_gcloud_cfg = os.getenv("GCLOUD_CFG_PATH")
project_id = os.getenv("PROJECT_ID")
deployment_name = os.getenv("DEPLOYMENT_NAME")
region = os.getenv("REGION")
zone = os.getenv("ZONE")
auth_cidr = os.getenv("AUTH_CIDR")
deployment_dir = os.getenv("DEPLOYMENT_DIR")


def create_gke_ml_blueprint() -> CtkBlueprint:
  """Create a simple gke cluster

  Returns:
      CtkBlueprint: blueprint of cluster to create
  """
  assert project_id is not None
  assert deployment_name is not None
  assert region is not None
  assert zone is not None
  assert auth_cidr is not None

  network1 = CtkDeploymentModule(
      id="network1",
      source="modules/network/vpc",
      settings={
          "subnetwork_name": f"{deployment_name}-gke-subnet",
          "secondary_ranges": {
              f"{deployment_name}-gke-subnet": [
                  {"range_name": "pods", "ip_cidr_range": "10.4.0.0/14"},
                  {
                      "range_name": "services",
                      "ip_cidr_range": "10.0.32.0/20",
                  },
              ]
          },
      },
  )

  gke_cluster = CtkDeploymentModule(
      id="gke_cluster",
      source="modules/scheduler/gke-cluster",
      use=["network1"],
      settings={
          "enable_private_endpoint": (
              "false"
          ),  # Allows for access from authorized public IPs
          "master_authorized_networks": [{
              "display_name": "deployment-machine",
              "cidr_block": auth_cidr,
          }],
      },
      outputs=["instructions"],
  )

  primary_group = CtkDeploymentGroup(
      group="primary",
      modules=[network1, gke_cluster],
  )
  ml_gke = CtkBlueprint(
      blueprint_name="ml_gke",
      deployment_groups=[primary_group],
      vars={
          "project_id": project_id,
          "deployment_name": deployment_name,
          "region": region,
      },
  )
  return ml_gke


@pytest.mark.skip(
    reason=(
        "Passing credentials from github actions to docker container do not"
        " work currently."
    )
)
def test_create_ctk_deployment():
  assert project_id is not None
  assert deployment_name is not None
  assert region is not None
  assert zone is not None
  assert auth_cidr is not None
  assert deployment_dir is not None
  assert ctk_gcloud_cfg is not None

  blueprint = create_gke_ml_blueprint()

  deployment_type = "test"

  deployment_type_dir = create_deployment_directory(
      blueprint=blueprint,
      deployment_type=deployment_type,
      deployment_directory=deployment_dir,
  )

  docker_manager = CtkDockerManager(
      gcloud_cfg_path=ctk_gcloud_cfg, deployment_dir=deployment_type_dir
  )
  docker_manager.build()

  ctk_manager = CtkManager(
      ctk_cmd_runner=docker_manager,
      deployment_dir=deployment_type_dir,
      deployment_name=deployment_name,
      deployment_type=deployment_type,
  )

  ctk_manager.stage_files()

  ctk_manager.deploy()
  assert os.path.exists(os.path.join(deployment_dir, deployment_name))
  ctk_manager.destroy_deployment()
