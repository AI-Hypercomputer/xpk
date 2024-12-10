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

from dataclasses import dataclass
import shutil
from typing import Any, Optional
from ruamel import yaml
import os

yaml = yaml.YAML()
blueprint_dependencies_dir = "src/xpk/blueprints/a3mega"


@dataclass
class DeploymentModule:
  """DeploymentModule represents cluster toolkit deployment module

  Attributes:
    id (str): module name
    source (str): cluster toolkit source
    settings (dict[str, Any]): module settings
    use (list[str]): modules on which module depends
    outputs (list[str]): module outputs in cluster toolkit
  """

  id: str
  source: str
  outputs: Optional[list[str]] = None
  settings: Optional[dict[str, Any]] = None
  use: Optional[list[str]] = None


@dataclass
class DeploymentGroup:
  """DeploymentGroup represents cluster toolkit deployment group

  Attributes:
    group (str): deployment group name
    modules (list[DeploymentModule]): deployments modules
  """

  modules: list[DeploymentModule]
  group: Optional[str]


@dataclass
class Blueprint:
  """A class to represent Cluster Toolkit blueprint"""

  vars: dict[str, str | list[str]]
  deployment_groups: list[DeploymentGroup]
  blueprint_name: Optional[str]


yaml.register_class(Blueprint)
yaml.register_class(DeploymentGroup)
yaml.register_class(DeploymentModule)


class BlueprintGeneratorOutput:

  def __init__(self, blueprint_file: str, blueprint_dependencies: str) -> None:
    self.blueprint_file = blueprint_file
    self.blueprint_dependencies = blueprint_dependencies


class BlueprintGenerator:
  """BlueprintGenerator is a class for generating blueprints
  Atributes:
  - storage_path (str) - path to TODO
  """

  def __init__(self, storage_path: str) -> None:
    self.storage_path = storage_path

  def generate_a3_mega_blueprint(
      self,
      cluster_name: str,
      project_id: str,
      blueprint_name: str,
      region: str,
      zone: str,
      auth_cidr: str,
      num_nodes: int = 2,
      pods_ip_cidr_range: str = "10.4.0.0/14",
      services_ip_cidr_range: str = "10.0.32.0/20",
      global_ip_address_range: str = "192.169.0.0/16",
      system_node_pool_machine_type: str = "e2-standard-32",
      num_chips: int = 32,
      primary_vpc_name: str = "network1",
      gpu_subnets_name: str = "gpunets",
  ) -> BlueprintGeneratorOutput:
    """Create A3 mega blueprint.

    Args:
    Returns:
      - Blueprint representing cluster toolkit blueprint
    """
    subnetwork_name = f"{cluster_name}-xpk-gke-a3-megagpu-subnet"
    primary_vpc = DeploymentModule(
        id=primary_vpc_name,
        source="modules/network/vpc",
        settings={
            "subnetwork_name": subnetwork_name,
            "secondary_ranges": {
                subnetwork_name: [
                    {"range_name": "pods", "ip_cidr_range": pods_ip_cidr_range},
                    {
                        "range_name": "services",
                        "ip_cidr_range": services_ip_cidr_range,
                    },
                ]
            },
        },
    )
    gpunets = DeploymentModule(
        id=gpu_subnets_name,
        source="modules/network/multivpc",
        settings={
            "network_name_prefix": f"{cluster_name}-gpunet",
            "global_ip_address_range": global_ip_address_range,
            "network_count": 8,
            "subnetwork_cidr_suffix": 24,
        },
    )

    gke_cluster = DeploymentModule(
        id="gke_cluster",
        source="modules/scheduler/gke-cluster",
        use=[primary_vpc_name, gpu_subnets_name],
        settings={
            "prefix_with_deployment_name": False,
            "name_suffix": cluster_name,
            "enable_private_endpoint": False,
            "master_authorized_networks": [{
                "cidr_block": (
                    f"{auth_cidr}"
                ),  # Allows your machine run kubectl command. It's required for the multi-network setup.
                "display_name": "kubectl-access-network",
            }],
            "system_node_pool_machine_type": system_node_pool_machine_type,
        },
        outputs=["instructions"],
    )

    group_placement_0 = DeploymentModule(
        id="group_placement_0",
        source="modules/compute/resource-policy",
        settings={
            "name": f"{cluster_name}-gp-np-0",
            "group_placement_max_distance": 2,
        },
    )

    group_placement_1 = DeploymentModule(
        id="group_placement_1",
        source="modules/compute/resource-policy",
        settings={
            "name": f"{cluster_name}-gp-np-1",
            "group_placement_max_distance": 2,
        },
    )

    a3_megagpu_pool_0 = DeploymentModule(
        id="a3_megagpu_pool_0",
        source="modules/compute/gke-node-pool",
        use=["gke_cluster", gpu_subnets_name, "group_placement_0"],
        settings={
            "name": f"{cluster_name}-a3-megagpu-pool-0",
            "machine_type": "a3-megagpu-8g",
            "autoscaling_total_min_nodes": 2,
            "initial_node_count": num_nodes,
            "zones": [zone],
            "host_maintenance_interval": "PERIODIC",
        },
        outputs=["instructions"],
    )

    a3_megagpu_pool_1 = DeploymentModule(
        id="a3_megagpu_pool_1",
        source="modules/compute/gke-node-pool",
        use=["gke_cluster", gpu_subnets_name, "group_placement_1"],
        settings={
            "name": f"{cluster_name}-a3-megagpu-pool-1",
            "machine_type": "a3-megagpu-8g",
            "autoscaling_total_min_nodes": 2,
            "initial_node_count": num_nodes,
            "zones": [zone],
            "host_maintenance_interval": "PERIODIC",
        },
        outputs=["instructions"],
    )

    workload = DeploymentModule(
        id="workload_component_install",
        source="modules/management/kubectl-apply",
        use=["gke_cluster"],
        settings={
            "kueue": {
                "install": True,
                "config_path": '$(ghpc_stage("a3-mega-xpk"))/kueue-xpk-configuration.yaml.tftpl',
                "config_template_vars": {"num_chips": f"{num_chips}"},
            },
            "jobset": {"install": True},
        },
    )

    topology_scheduler = DeploymentModule(
        id="topology_aware_scheduler_install",
        source="community/modules/compute/gke-topology-scheduler",
        use=["gke_cluster"],
    )

    workload_configmap = DeploymentModule(
        id="workload_configmap",
        source="modules/management/kubectl-apply",
        use=["gke_cluster"],
        settings={
            "apply_manifests": [{
                "source": '$(ghpc_stage("a3-mega-xpk"))/config-map.yaml.tftpl',
                "template_vars": {
                    "name": "xpk-gke-a3-megagpu-resources-configmap",
                    "num_nodes": "4",
                },
            }]
        },
    )
    primary_group = DeploymentGroup(
        group="primary",
        modules=[
            primary_vpc,
            gpunets,
            gke_cluster,
            group_placement_0,
            group_placement_1,
            a3_megagpu_pool_0,
            a3_megagpu_pool_1,
            workload,
            topology_scheduler,
            workload_configmap,
        ],
    )
    xpk_blueprint = Blueprint(
        blueprint_name=blueprint_name,
        deployment_groups=[primary_group],
        vars={
            "project_id": project_id,
            "deployment_name": blueprint_name,
            "region": region,
            "zone": zone,
        },
    )
    blueprint_file_path = self._save_blueprint_to_file(
        blueprint_name, xpk_blueprint
    )
    blueprint_dependencies = self._get_a3_mega_blueprint_dependencies(
        blueprint_name
    )
    return BlueprintGeneratorOutput(
        blueprint_file=blueprint_file_path,
        blueprint_dependencies=blueprint_dependencies,
    )

  def generate_gke_ml_blueprint(
      self,
      cluster_name: str,
      blueprint_name: str,
      project_id: str,
      region: str,
      auth_cidr: str,
  ) -> BlueprintGeneratorOutput:
    """Create a simple gke cluster

    Returns:
        Blueprint: blueprint of cluster to create
    """

    network1 = DeploymentModule(
        id="network1",
        source="modules/network/vpc",
        settings={
            "subnetwork_name": f"{blueprint_name}-gke-subnet",
            "secondary_ranges": {
                f"{blueprint_name}-gke-subnet": [
                    {"range_name": "pods", "ip_cidr_range": "10.4.0.0/14"},
                    {
                        "range_name": "services",
                        "ip_cidr_range": "10.0.32.0/20",
                    },
                ]
            },
        },
    )

    gke_cluster = DeploymentModule(
        id="gke_cluster",
        source="modules/scheduler/gke-cluster",
        use=["network1"],
        settings={
            "prefix_with_deployment_name": False,
            "name_suffix": cluster_name,
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

    primary_group = DeploymentGroup(
        group="primary",
        modules=[network1, gke_cluster],
    )
    ml_gke = Blueprint(
        blueprint_name=blueprint_name,
        deployment_groups=[primary_group],
        vars={
            "project_id": project_id,
            "deployment_name": blueprint_name,
            "region": region,
        },
    )
    blueprint_file_path = self._save_blueprint_to_file(blueprint_name, ml_gke)
    blueprint_dependencies = ""
    return BlueprintGeneratorOutput(
        blueprint_file=blueprint_file_path,
        blueprint_dependencies=blueprint_dependencies,
    )

  def _save_blueprint_to_file(
      self, blueprint_name: str, xpk_blueprint: Blueprint
  ) -> str:
    blueprint_path = os.path.join(self.storage_path, f"{blueprint_name}.yaml")
    with open(blueprint_path, "w+", encoding="utf-8") as blueprint_file:
      yaml.dump(xpk_blueprint, blueprint_file)
    return blueprint_path

  def _get_a3_mega_blueprint_dependencies(self, blueprint_name: str) -> str:
    deployment_files_path = os.path.join(self.storage_path, blueprint_name)
    shutil.copytree(blueprint_dependencies_dir, deployment_files_path)
    return deployment_files_path
