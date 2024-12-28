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
from ruamel import yaml
import os
from .blueprint_definitions import DeploymentGroup, DeploymentModule, Blueprint
from ..system_characteristics import get_system_characteristics_by_device_type
from ...utils.console import xpk_print, xpk_exit
from ...utils.file import ensure_directory_exists
from ..core import CapacityType

yaml = yaml.YAML()

a3mega_device_type = "h100-mega-80gb-8"

supported_device_types = {a3mega_device_type}
blueprint_dependencies_dir = {a3mega_device_type: "src/xpk/blueprints/a3mega"}


class BlueprintGeneratorOutput:
  """BlueprintGeneratorOutput is a class containing fields with output blueprint file path and path to blueprint dependencies.
  Atributes:
  - blueprint_file (str) : path to generated blueprint file.
  - blueprint_dependencies (str) : path to directory containing blueprint dependencies.
  """

  def __init__(self, blueprint_file: str, blueprint_dependencies: str) -> None:
    self.blueprint_file = blueprint_file
    self.blueprint_dependencies = blueprint_dependencies


class BlueprintGenerator:
  """BlueprintGenerator is a class for generating blueprints
  Atributes:
  - storage_path (str) - path to directory where generated files and directories will be stored.
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
      prefix: str = "",
      num_nodes: int = 2,
      pods_ip_cidr_range: str = "10.4.0.0/14",
      services_ip_cidr_range: str = "10.0.32.0/20",
      global_ip_address_range: str = "192.169.0.0/16",
      system_node_pool_machine_type: str = "e2-standard-32",
      primary_vpc_name: str = "network1",
      gpu_subnets_name: str = "gpunets",
      group_placement_max_distance: int = 2,
      subnetwork_cidr_suffix: int = 24,
      reservation: str | None = None,
      capacity_type: CapacityType = CapacityType.ON_DEMAND,
      system_node_pool_min_node_count: int = 2,
  ) -> BlueprintGeneratorOutput:
    """Create A3 mega blueprint and directory containing its dependencies.

    Returns:
      - BlueprintGeneratorOutput object containing path to blueprint and its dependencies.
    """
    xpk_print(f"Generating {blueprint_name} blueprint started...")
    system, _ = get_system_characteristics_by_device_type(a3mega_device_type)
    if system is None:
      xpk_print(
          "Error: Could not retrieve system characteristics for"
          f" {a3mega_device_type} device_type."
      )
      xpk_exit(1)
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
            "subnetwork_cidr_suffix": subnetwork_cidr_suffix,
        },
    )

    gke_cluster = DeploymentModule(
        id="gke_cluster",
        source="modules/scheduler/gke-cluster",
        use=[primary_vpc_name, gpu_subnets_name],
        settings={
            "release_channel": "RAPID",
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
            "system_node_pool_node_count": {
                "total_min_nodes": system_node_pool_min_node_count,
                "total_max_nodes": 1000,
            },
        },
        outputs=["instructions"],
    )

    group_placement_0 = DeploymentModule(
        id="group_placement_0",
        source="modules/compute/resource-policy",
        settings={
            "name": f"{cluster_name}-gp-np-0",
            "group_placement_max_distance": group_placement_max_distance,
        },
    )

    reservation_affinity = (
        {
            "consume_reservation_type": "NO_RESERVATION",
            "specific_reservations": [],
        }
        if reservation is None
        else {
            "consume_reservation_type": "SPECIFIC_RESERVATION",
            "specific_reservations": [{"name": reservation}],
        }
    )

    a3_megagpu_pool_0 = DeploymentModule(
        id="a3_megagpu_pool_0",
        source="modules/compute/gke-node-pool",
        use=["gke_cluster", gpu_subnets_name, "group_placement_0"],
        settings={
            "name": f"{cluster_name}-a3-megagpu-pool-0",
            "machine_type": system.gce_machine_type,
            "static_node_count": num_nodes,
            "zones": [zone],
            "host_maintenance_interval": "PERIODIC",
            "reservation_affinity": reservation_affinity,
            "run_workload_script": False,
            "spot": capacity_type == CapacityType.SPOT,
            "max_pods_per_node": 32,
            "auto_upgrade": True,
        },
        outputs=["instructions"],
    )
    num_chips = num_nodes * system.chips_per_vm
    workload = DeploymentModule(
        id="workload_component_install",
        source="modules/management/kubectl-apply",
        use=["gke_cluster"],
        settings={
            "kueue": {
                "install": True,
                "version": "v0.10.0",  # TAS feature-gates is enabled in CT
                "config_path": f'$(ghpc_stage("{blueprint_name}"))/kueue-xpk-configuration.yaml.tftpl',
                "config_template_vars": {"num_chips": f"{num_chips}"},
            },
            "jobset": {"install": True},
        },
    )

    workload_configmap = DeploymentModule(
        id="workload_configmap",
        source="modules/management/kubectl-apply",
        use=["gke_cluster"],
        settings={
            "apply_manifests": [{
                "source": (
                    f'$(ghpc_stage("{blueprint_name}"))/config-map.yaml.tftpl'
                ),
                "template_vars": {
                    "resource_config_name": (
                        f"{cluster_name}-resources-configmap"
                    ),
                    "num_nodes": f"{num_nodes}",
                    "cluster_config_name": f"{cluster_name}-metadata-configmap",
                    "capacity_type": f"{capacity_type}",
                    "reservation": f"{reservation}",
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
            a3_megagpu_pool_0,
            workload,
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
        blueprint_name, xpk_blueprint, prefix
    )
    blueprint_dependencies = self._get_a3_mega_blueprint_dependencies(
        blueprint_name, prefix
    )
    xpk_print(f"Blueprint file path: {blueprint_file_path}")
    xpk_print(
        f"Blueprint dependencies directory path: {blueprint_dependencies}"
    )
    xpk_print(f"The {blueprint_name} blueprint generated.")
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
      prefix: str = "",
  ) -> BlueprintGeneratorOutput:
    """Create a simple gke cluster

    Returns:
        Blueprint: blueprint of simple cluster to create. This blueprint doesn't have any dependencies.
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
    blueprint_file_path = self._save_blueprint_to_file(
        blueprint_name, ml_gke, prefix
    )
    blueprint_dependencies = ""
    return BlueprintGeneratorOutput(
        blueprint_file=blueprint_file_path,
        blueprint_dependencies=blueprint_dependencies,
    )

  def _save_blueprint_to_file(
      self, blueprint_name: str, xpk_blueprint: Blueprint, prefix: str = ""
  ) -> str:
    blueprint_path = self._get_blueprint_path(blueprint_name, prefix)
    with open(blueprint_path, "w+", encoding="utf-8") as blueprint_file:
      yaml.dump(xpk_blueprint, blueprint_file)
    return blueprint_path

  def _get_blueprint_path(self, blueprint_name, prefix: str = ""):
    blueprint_path = os.path.join(
        self._get_storage_path(prefix), f"{blueprint_name}.yaml"
    )
    return blueprint_path

  def _get_storage_path(self, prefix):
    storage_path_with_prefix = os.path.join(self.storage_path, prefix)
    ensure_directory_exists(storage_path_with_prefix)
    return storage_path_with_prefix

  def blueprint_exists(self, blueprint_name, prefix: str = ""):
    blueprint_path = self._get_blueprint_path(blueprint_name, prefix)
    return os.path.exists(blueprint_path)

  def _get_a3_mega_blueprint_dependencies(
      self, blueprint_name: str, prefix: str = ""
  ) -> str:
    deployment_files_path = os.path.join(
        self._get_storage_path(prefix), blueprint_name
    )
    shutil.copytree(
        blueprint_dependencies_dir[a3mega_device_type],
        deployment_files_path,
        dirs_exist_ok=True,
    )
    return deployment_files_path


yaml.register_class(Blueprint)
yaml.register_class(DeploymentGroup)
yaml.register_class(DeploymentModule)
