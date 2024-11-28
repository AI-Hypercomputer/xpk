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
from xpk.core.blueprint import CtkBlueprint, CtkDeploymentGroup, CtkDeploymentModule, save_blueprint_to_yaml_file
from xpk.core.gcluster import blueprint_file_name
import os

ctk_dockerfile_gh = "https://github.com/GoogleCloudPlatform/cluster-toolkit/blob/develop/tools/cloud-build/images/cluster-toolkit-dockerfile/Dockerfile"
ctk_gcloud_cfg = "/gcloud/cfg"
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
          "subnetwork_name": "gke-subnet",
          "secondary_ranges": {
              "gke-subnet": [
                  {"range_name": "pods", "ip_cidr_range": "10.4.0.0/14"},
                  {
                      "range_name": "services",
                      "ip_cidr_range": "10.0.32.0/20",
                  },
              ]
          },
      },
  )
  sa = CtkDeploymentModule(
      id="gke_sa",
      source="community/modules/project/service-account",
      settings={
          "name": "gke-sa",
          "project_roles": [
              "logging.logWriter",
              "monitoring.metricWriter",
              "monitoring.viewer",
              "stackdriver.resourceMetadata.writer",
              "storage.objectViewer",
              "artifactregistry.reader",
          ],
      },
  )

  gke_cluster = CtkDeploymentModule(
      id="gke_cluster",
      source="modules/scheduler/gke-cluster",
      use=["network1", "gke-sa"],
      settings={
          "enable_private_endpoint": (
              "false"
          ),  # Allows for access from authorized public IPs
          "master_authorized_networks": [
              {"display_name": "deployment-machine"}
          ],
          "cidr_block": auth_cidr,
          "configure_workload_identity_sa": "true",
      },
      outputs=["instructions"],
  )
  gke_cluster = CtkDeploymentModule(
      id="gke_cluster",
      source="modules/scheduler/gke-cluster",
      use=["network1", "gke-sa"],
      settings={
          "enable_private_endpoint": (
              "false"
          ),  # Allows for access from authorized public IPs
          "master_authorized_networks": [{
              "display_name": "deployment-machine",
              "cidr_block": auth_cidr,
          }],
          "configure_workload_identity_sa": "true",
      },
      outputs=["instructions"],
  )
  g2_pool = CtkDeploymentModule(
      id="g2_pool",
      source="modules/scheduler/gke-cluster",
      use=["gke_cluster", "gke-sa"],
      settings={"disk_type": "pd-balanced", "machine_type": "g2-standard-4"},
  )
  job_template = CtkDeploymentModule(
      id="job_template",
      source="modules/compute/gke-job-template",
      use=["g2_pool"],
      settings={
          "image": "nvidia/cuda:11.0.3-runtime-ubuntu20.04",
          "command": ["nvidia-smi"],
          "node_count": 1,
      },
  )
  primary_group = CtkDeploymentGroup(
      group="primary",
      modules=[network1, sa, g2_pool, gke_cluster, job_template],
  )
  ml_gke = CtkBlueprint(
      blueprint_name="ml_gke",
      deployment_groups=[primary_group],
      vars={
          "project_id": project_id,
          "deployment_name": deployment_name,
          "region": region,
          "zones": zone,
          "authorized_cidr": auth_cidr,
      },
  )
  return ml_gke


def test_create_ctk_deployment():
  assert project_id is not None
  assert deployment_name is not None
  assert region is not None
  assert zone is not None
  assert auth_cidr is not None
  assert deployment_dir is not None

  blueprint = create_gke_ml_blueprint()
  blueprint_path = os.path.join(deployment_dir, blueprint_file_name)
  save_blueprint_to_yaml_file(yaml_path=blueprint_path, blueprint=blueprint)

  docker_manager = CtkDockerManager(
      gcloud_cfg_path=ctk_gcloud_cfg, deployment_dir=deployment_dir
  )

  ctk_manager = CtkManager(
      ctk_cmd_runner=docker_manager, deployment_dir=deployment_dir
  )

  ctk_manager.deploy()
