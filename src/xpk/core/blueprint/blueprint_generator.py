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
from typing import Optional

from ruamel import yaml

from ...utils.console import xpk_exit, xpk_print
from ...utils.file import ensure_directory_exists
from ..capacity import H100_MEGA_DEVICE_TYPE, H200_DEVICE_TYPE, CapacityType
from ..system_characteristics import get_system_characteristics_by_device_type
from .blueprint_definitions import Blueprint, DeploymentGroup, DeploymentModule

yaml = yaml.YAML()

a3mega_device_type = H100_MEGA_DEVICE_TYPE
a3ultra_device_type = H200_DEVICE_TYPE
supported_device_types = {a3mega_device_type, a3ultra_device_type}
blueprint_dependencies_dir = {
    a3mega_device_type: "src/xpk/blueprints/a3mega",
    a3ultra_device_type: "src/xpk/blueprints/a3ultra",
}

cluster_toolkit_url = "github.com/GoogleCloudPlatform/cluster-toolkit"
cluster_toolkit_version = "v1.45.1"


def get_subnetworks_for_a3mega(cluster_name: str) -> list[str]:
  return [f"{cluster_name}-gpunet-{i}-subnet" for i in range(8)]


def get_subnetworks_for_a3ultra(cluster_name: str) -> list[str]:
  return [f"{cluster_name}-sub-1"] + [
      f"{cluster_name}-rdma-sub-{i}" for i in range(8)
  ]


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
      gcs_bucket: Optional[str | None] = None,
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
            "enable_gcsfuse_csi": True,
            "enable_filestore_csi": True,
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
            "reservation_affinity": self._getblock_reservation_affinity(
                reservation
            ),
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
            "jobset": {"install": True, "version": "v0.7.2"},
            "apply_manifests": [{
                "source": f'$(ghpc_stage("{blueprint_name}"))/storage_crd.yaml'
            }],
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
                    "capacity_type": f"{capacity_type.value}",
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
    a3_mega_blueprint = Blueprint(
        terraform_backend_defaults=self._getblock_terraform_backend(
            gcs_bucket, prefix
        ),
        blueprint_name=blueprint_name,
        toolkit_modules_url=cluster_toolkit_url,
        toolkit_modules_version=cluster_toolkit_version,
        deployment_groups=[primary_group],
        vars={
            "project_id": project_id,
            "deployment_name": blueprint_name,
            "region": region,
            "zone": zone,
        },
    )

    blueprint_file_path = self._save_blueprint_to_file(
        blueprint_name, a3_mega_blueprint, prefix
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
      gcs_bucket: Optional[str | None] = None,
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
        terraform_backend_defaults=self._getblock_terraform_backend(
            gcs_bucket, prefix
        ),
        blueprint_name=blueprint_name,
        toolkit_modules_url=cluster_toolkit_url,
        toolkit_modules_version=cluster_toolkit_version,
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

  def generate_a3_ultra_blueprint(
      self,
      project_id: str,
      cluster_name: str,
      blueprint_name: str,
      region: str,
      zone: str,
      auth_cidr: str,
      system_node_pool_machine_type: str,
      reservation: Optional[str | None] = None,
      gcs_bucket: Optional[str | None] = None,
      num_nodes: int = 2,
      enable_filestore_csi_driver=True,
      prefix: str = "",
      mtu_size: int = 8896,
      system_node_pool_min_node_count: int = 2,
      capacity_type: CapacityType = CapacityType.ON_DEMAND,
  ) -> BlueprintGeneratorOutput:
    """Create A3 ultra blueprint.

    Args:
    Returns:
      - Blueprint representing cluster toolkit blueprint
    """

    nccl_installer_path = (
        f'$(ghpc_stage("{blueprint_name}"))/nccl-installer.yaml'
    )
    mlgru_disable_path = f'$(ghpc_stage("{blueprint_name}"))/mlgru-disable.yaml'
    net_0_id = f"{cluster_name}-net-0"
    gpu_net_0 = DeploymentModule(
        id=net_0_id,
        source="modules/network/vpc",
        settings={
            "network_name": f"{cluster_name}-net-0",
            "subnetworks": [{
                "subnet_name": f"{cluster_name}-sub-0",
                "subnet_region": region,
                "subnet_ip": "192.168.0.0/18",
            }],
            "secondary_ranges_list": [{
                "subnetwork_name": f"{cluster_name}-sub-0",
                "ranges": [
                    {"range_name": "pods", "ip_cidr_range": "10.4.0.0/14"},
                    {"range_name": "services", "ip_cidr_range": "10.0.32.0/20"},
                ],
            }],
            "firewall_rules": [{
                "name": f"{cluster_name}-internal-0",
                "ranges": ["192.168.0.0/16"],
                "allow": [
                    {"protocol": "tcp", "ports": ["0-65535"]},
                    {"protocol": "udp", "ports": ["0-65535"]},
                    {"protocol": "icmp"},
                ],
            }],
        },
    )
    net_1_id = f"{cluster_name}-net-1"
    gpu_net_1 = DeploymentModule(
        id=net_1_id,
        source="modules/network/vpc",
        settings={
            "network_name": f"{cluster_name}-net-1",
            "mtu": mtu_size,
            "subnetworks": [{
                "subnet_name": f"{cluster_name}-sub-1",
                "subnet_region": region,
                "subnet_ip": "192.168.64.0/18",
            }],
            "firewall_rules": [{
                "name": f"{cluster_name}-internal-1",
                "ranges": ["192.168.0.0/16"],
                "allow": [
                    {"protocol": "tcp", "ports": ["0-65535"]},
                    {"protocol": "udp", "ports": ["0-65535"]},
                    {"protocol": "icmp"},
                ],
            }],
        },
    )
    rma_net_id = f"{cluster_name}-rdma-net"
    rma_net = DeploymentModule(
        id=rma_net_id,
        source="modules/network/gpu-rdma-vpc",
        settings={
            "network_name": f"{cluster_name}-rdma-net",
            "mtu": mtu_size,
            "network_profile": f"https://www.googleapis.com/compute/beta/projects/{project_id}/global/networkProfiles/{zone}-vpc-roce",
            "network_routing_mode": "REGIONAL",
            "subnetworks_template": {
                "name_prefix": f"{cluster_name}-rdma-sub",
                "count": 8,
                "ip_range": "192.168.128.0/18",
                "region": region,
            },
        },
    )
    cluster_id = f"{cluster_name}-a3-ultragpu-cluster"
    a3_ultra_cluster = DeploymentModule(
        id=cluster_id,
        source="modules/scheduler/gke-cluster",
        use=[net_0_id],
        settings={
            "release_channel": "RAPID",
            "version_prefix": "1.31.",
            "maintenance_exclusions": [{
                "name": "no-minor-or-node-upgrades-indefinite",
                "start_time": "2024-12-01T00:00:00Z",
                "end_time": "2025-12-22T00:00:00Z",
                "exclusion_scope": "NO_MINOR_OR_NODE_UPGRADES",
            }],
            "prefix_with_deployment_name": False,
            "name_suffix": cluster_name,
            "system_node_pool_machine_type": system_node_pool_machine_type,
            "enable_dcgm_monitoring": True,
            "enable_gcsfuse_csi": True,
            "enable_filestore_csi": enable_filestore_csi_driver,
            "enable_private_endpoint": False,
            "master_authorized_networks": [{
                "cidr_block": auth_cidr,
                "display_name": "kubectl-access-network",
            }],
            "system_node_pool_node_count": {
                "total_min_nodes": system_node_pool_min_node_count,
                "total_max_nodes": 1000,
            },
            "additional_networks": (
                f"$(concat([{{network={cluster_name}-net-1.network_name,"
                f" subnetwork={cluster_name}-net-1.subnetwork_name,"
                f' subnetwork_project="{project_id}", nic_type="GVNIC",'
                " queue_count=null, network_ip=null, stack_type=null,"
                " access_config=[{nat_ip=null, public_ptr_domain_name=null,"
                " network_tier=null}], ipv6_access_config=[],"
                " alias_ip_range=[]}],"
                f" {cluster_name}-rdma-net.subnetwork_interfaces_gke))"
            ),
        },
        outputs=["instructions"],
    )
    system, _ = get_system_characteristics_by_device_type(a3ultra_device_type)
    if system is None:
      xpk_print(
          "Error: Could not retrieve system characteristics for"
          f" {a3ultra_device_type} device_type."
      )
      xpk_exit(1)
    gpu_pool = DeploymentModule(
        id=f"{cluster_name}-a3u-pool",
        source="modules/compute/gke-node-pool",
        use=[cluster_id],
        settings={
            "machine_type": system.gce_machine_type,
            "auto_upgrade": True,
            "zones": [zone],
            "static_node_count": num_nodes,
            "spot": capacity_type == CapacityType.SPOT,
            "reservation_affinity": self._getblock_reservation_affinity(
                reservation
            ),
            "max_pods_per_node": 32,
            "guest_accelerator": [{
                "type": "nvidia-h200-141gb",
                "count": 8,
                "gpu_driver_installation_config": {
                    "gpu_driver_version": "LATEST"
                },
            }],
            "additional_networks": (
                f"$(concat([{{network={cluster_name}-net-1.network_name,"
                f" subnetwork={cluster_name}-net-1.subnetwork_name,"
                f' subnetwork_project="{project_id}", nic_type="GVNIC",'
                " queue_count=null, network_ip=null, stack_type=null,"
                " access_config=[{nat_ip=null, public_ptr_domain_name=null,"
                " network_tier=null}], ipv6_access_config=[],"
                " alias_ip_range=[]}],"
                f" {cluster_name}-rdma-net.subnetwork_interfaces_gke))"
            ),
        },
        outputs=["instructions"],
    )

    num_chips = num_nodes * system.chips_per_vm
    workload_manager_install_id = "workload-manager-install"
    workload_manager_install = DeploymentModule(
        id=workload_manager_install_id,
        source="modules/management/kubectl-apply",
        use=[cluster_id],
        settings={
            "kueue": {
                "install": True,
                "version": "v0.10.0",  # TAS feature-gates is enabled in CT
                "config_path": f'$(ghpc_stage("{blueprint_name}"))/kueue-xpk-configuration.yaml.tftpl',
                "config_template_vars": {"num_chips": f"{num_chips}"},
            },
            "jobset": {"install": True, "version": "v0.7.2"},
            "apply_manifests": [
                {"source": nccl_installer_path},
                {"source": mlgru_disable_path},
                {
                    "source": (
                        f'$(ghpc_stage("{blueprint_name}"))/storage_crd.yaml'
                    )
                },
            ],
        },
    )

    workload_configmap = DeploymentModule(
        id="workload_configmap",
        source="modules/management/kubectl-apply",
        use=[cluster_id],
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
                    "capacity_type": f"{capacity_type.value}",
                    "reservation": f"{reservation}",
                },
            }]
        },
    )

    primary_group = DeploymentGroup(
        group="primary",
        modules=[
            gpu_net_0,
            gpu_net_1,
            rma_net,
            a3_ultra_cluster,
            gpu_pool,
            workload_manager_install,
            workload_configmap,
        ],
    )
    a3_ultra_blueprint = Blueprint(
        terraform_backend_defaults=self._getblock_terraform_backend(
            gcs_bucket, prefix
        ),
        blueprint_name=blueprint_name,
        toolkit_modules_url=cluster_toolkit_url,
        toolkit_modules_version=cluster_toolkit_version,
        deployment_groups=[primary_group],
        vars={
            "project_id": project_id,
            "deployment_name": blueprint_name,
            "region": region,
            "zone": zone,
        },
    )

    blueprint_file_path = self._save_blueprint_to_file(
        blueprint_name, a3_ultra_blueprint, prefix
    )
    blueprint_dependencies = self._get_a3_ultra_blueprint_dependencies(
        blueprint_name, prefix
    )
    return BlueprintGeneratorOutput(
        blueprint_file=blueprint_file_path,
        blueprint_dependencies=blueprint_dependencies,
    )

  def _getblock_reservation_affinity(
      self, reservation: str | None = None
  ) -> dict:
    return (
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

  def _getblock_terraform_backend(
      self, gcs_bucket: str, prefix: str = ""
  ) -> dict | None:
    if gcs_bucket is None:
      return None
    return {
        "type": "gcs",
        "configuration": {
            "bucket": gcs_bucket,
            "prefix": self._get_terraforrm_backend_full_prefix(prefix),
        },
    }

  def _get_terraforrm_backend_full_prefix(self, prefix: str = "") -> str:
    return f"xpk_terraform_state/{prefix}/tfstate/"

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

  def _get_a3_ultra_blueprint_dependencies(
      self, blueprint_name: str, prefix: str = ""
  ) -> str:
    deployment_files_path = os.path.join(
        self._get_storage_path(prefix), blueprint_name
    )
    shutil.copytree(
        blueprint_dependencies_dir[a3ultra_device_type],
        deployment_files_path,
        dirs_exist_ok=True,
    )
    return deployment_files_path


yaml.register_class(Blueprint)
yaml.register_class(DeploymentGroup)
yaml.register_class(DeploymentModule)
