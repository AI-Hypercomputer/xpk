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

yaml = yaml.YAML()
a3mega_blueprint_dependencies_dir = "src/xpk/blueprints/a3mega"
a3_machine_type = "a3-megagpu-8g"


class BlueprintGeneratorOutput:
  """BlueprintGeneratorOutput is a class containing fields with output blueprint file path and path to blueprint dependencies.
  Atributes:
  - blueprint_file (str) : path to generated blueprint file.
  - blueprint_dependencies (str) : path to directory containing blueprint dependencies.
  """

  def __init__(self, blueprint_file: str, blueprint_dependencies: str) -> None:
    self.blueprint_file = blueprint_file
    self.blueprint_dependencies = blueprint_dependencies


machine_chipcount = {a3_machine_type: 8}


def get_num_chips(num_nodes: int, machine_type: str) -> int:
  return machine_chipcount[machine_type] * num_nodes


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
      num_nodes: int = 2,
      pods_ip_cidr_range: str = "10.4.0.0/14",
      services_ip_cidr_range: str = "10.0.32.0/20",
      global_ip_address_range: str = "192.169.0.0/16",
      system_node_pool_machine_type: str = "e2-standard-32",
      primary_vpc_name: str = "network1",
      gpu_subnets_name: str = "gpunets",
      group_placement_max_distance: int = 2,
      autoscaling_total_min_nodes: int = 2,
      gpunets_network_count: int = 8,
      subnetwork_cidr_suffix: int = 24,
  ) -> BlueprintGeneratorOutput:
    """Create A3 mega blueprint and directory containing its dependencies.

    Returns:
      - BlueprintGeneratorOutput object containing path to blueprint and its dependencies.
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
            "network_count": gpunets_network_count,
            "subnetwork_cidr_suffix": subnetwork_cidr_suffix,
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
            "group_placement_max_distance": group_placement_max_distance,
        },
    )

    a3_megagpu_pool_0 = DeploymentModule(
        id="a3_megagpu_pool_0",
        source="modules/compute/gke-node-pool",
        use=["gke_cluster", gpu_subnets_name, "group_placement_0"],
        settings={
            "name": f"{cluster_name}-a3-megagpu-pool-0",
            "machine_type": a3_machine_type,
            "autoscaling_total_min_nodes": autoscaling_total_min_nodes,
            "initial_node_count": num_nodes,
            "zones": [zone],
            "host_maintenance_interval": "PERIODIC",
        },
        outputs=["instructions"],
    )
    num_chips = get_num_chips(num_nodes, a3_machine_type)
    workload = DeploymentModule(
        id="workload_component_install",
        source="modules/management/kubectl-apply",
        use=["gke_cluster"],
        settings={
            "kueue": {
                "install": True,
                "config_path": f'$(ghpc_stage("{cluster_name}-a3-mega-xpk"))/kueue-xpk-configuration.yaml.tftpl',
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
                "source": f'$(ghpc_stage("{cluster_name}-a3-mega-xpk"))/config-map.yaml.tftpl',
                "template_vars": {
                    "name": "xpk-gke-a3-megagpu-resources-configmap",
                    "num_nodes": f"{num_nodes}",
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
    shutil.copytree(a3mega_blueprint_dependencies_dir, deployment_files_path)
    return deployment_files_path

  def generate_a3_ultra_blueprint(
      self,
      project_id: str,
      deployment_name: str,
      region: str,
      zone: str,
      mtu_size: int,
      gke_min_version: str,
      system_node_pool_disk_size_gb: int,
      auth_cidr: str,
      a3ultra_node_pool_disk_size_gb: int,
      static_node_count: int,
      extended_reservation: str,
  ) -> BlueprintGeneratorOutput:
    """Create A3 ultra blueprint.

    Args:
    Returns:
      - Blueprint representing cluster toolkit blueprint
    """

    nccl_installer_path = '$(ghpc_stage("./nccl-installer.yaml"))'
    mglru_disable_path = '$(ghpc_stage("./mglru-disable.yaml"))'
    net_0_id = "gke-a3-ultra-net-0"
    gpu_net_0 = DeploymentModule(
        id=net_0_id,
        source="github.com/GoogleCloudPlatform/cluster-toolkit.git//modules/network/vpc?ref=e0c690b",
        settings={
            "network_name": "gke-a3-ultra-net-0",
            "subnetworks": [{
                "subnet_name": "gke-a3-ultra-sub-0",
                "subnet_region": region,
                "subnet_ip": "192.168.0.0/18",
            }],
            "secondary_ranges": {
                "gke-a3-ultra-sub-0": [
                    {"range_name": "pods", "ip_cidr_range": "10.4.0.0/14"},
                    {"range_name": "services", "ip_cidr_range": "10.0.32.0/20"},
                ]
            },
            "firewall_rules": [{
                "name": "gke-a3-ultra-internal-0",
                "ranges": ["192.168.0.0/16"],
                "allow": [
                    {"protocol": "tcp", "ports": ["0-65535"]},
                    {"protocol": "udp", "ports": ["0-65535"]},
                    {"protocol": "icmp"},
                ],
            }],
        },
    )
    net_1_id = "gke-a3-ultra-net-1"
    gpu_net_1 = DeploymentModule(
        id=net_1_id,
        source="github.com/GoogleCloudPlatform/cluster-toolkit.git//modules/network/vpc?ref=e0c690b",
        settings={
            "network_name": "gke-a3-ultra-net-1",
            "mtu": mtu_size,
            "subnetworks": [{
                "subnet_name": "gke-a3-ultra-sub-1",
                "subnet_region": region,
                "subnet_ip": "192.168.64.0/18",
            }],
            "firewall_rules": [{
                "name": "gke-a3-ultra-internal-1",
                "ranges": ["192.168.0.0/16"],
                "allow": [
                    {"protocol": "tcp", "ports": ["0-65535"]},
                    {"protocol": "udp", "ports": ["0-65535"]},
                    {"protocol": "icmp"},
                ],
            }],
        },
    )
    rma_net_id = "gke-a3-ultra-rdma-net"
    rma_net = DeploymentModule(
        id=rma_net_id,
        source="github.com/GoogleCloudPlatform/cluster-toolkit.git//community/modules/network/rdma-vpc?ref=98c49fe",
        settings={
            "network_name": "gke-a3-ultra-rdma-net",
            "mtu": mtu_size,
            "network_profile": f"https://www.googleapis.com/compute/beta/projects/{project_id}/global/networkProfiles/{zone}-vpc-roce",
            "network_routing_mode": "REGIONAL",
            "subnetworks_template": {
                "name_prefix": "gke-a3-ultra-rdma-sub",
                "count": 8,
                "ip_range": "192.168.128.0/18",
                "region": region,
            },
        },
    )
    cluster_id = "a3-ultragpu-cluster"
    a3_ultra_cluster = DeploymentModule(
        id=cluster_id,
        source="github.com/GoogleCloudPlatform/cluster-toolkit.git//modules/scheduler/gke-cluster?ref=e0c690b",
        use=[net_0_id],
        settings={
            "min_master_version": gke_min_version,
            "system_node_pool_machine_type": "e2-standard-16",
            "system_node_pool_disk_size_gb": system_node_pool_disk_size_gb,
            "system_node_pool_taints": [],
            "enable_dcgm_monitoring": True,
            "enable_gcsfuse_csi": True,
            "enable_private_endpoint": False,
            "master_authorized_networks": [{
                "cidr_block": auth_cidr,
                "display_name": "kubectl-access-network",
            }],
            "additional_networks": (
                "$(concat([{network=gke-a3-ultra-net-1.network_name,"
                " subnetwork=gke-a3-ultra-net-1.subnetwork_name,"
                f' subnetwork_project={project_id}, nic_type="GVNIC",'
                " queue_count=null, network_ip=null, stack_type=null,"
                " access_config=[{nat_ip=null, public_ptr_domain_name=null,"
                " network_tier=null}], ipv6_access_config=[],"
                " alias_ip_range=[]}],"
                " gke-a3-ultra-rdma-net.subnetwork_interfaces_gke))"
            ),
        },
        outputs=["instructions"],
    )
    gpu_pool_id = "a3-ultragpu-pool"
    gpu_pool = DeploymentModule(
        id=gpu_pool_id,
        source="github.com/GoogleCloudPlatform/cluster-toolkit.git//modules/compute/gke-node-pool?ref=e0c690b",
        use=[cluster_id],
        settings={
            "machine_type": "a3-ultragpu-8g",
            "zones": [zone],
            "disk_type": "hyperdisk-balanced",
            "disk_size_gb": a3ultra_node_pool_disk_size_gb,
            "static_node_count": static_node_count,
            "guest_accelerator": [{
                "type": "nvidia-h200-141gb",
                "count": 8,
                "gpu_driver_installation_config": {
                    "gpu_driver_version": "LATEST"
                },
            }],
            "reservation_affinity": {
                "consume_reservation_type": "SPECIFIC_RESERVATION",
                "specific_reservations": [{"name": extended_reservation}],
            },
            "additional_networks": (
                "$(concat([{network=gke-a3-ultra-net-1.network_name,"
                " subnetwork=gke-a3-ultra-net-1.subnetwork_name,"
                f' subnetwork_project={project_id}, nic_type="GVNIC",'
                " queue_count=null, network_ip=null, stack_type=null,"
                " access_config=[{nat_ip=null, public_ptr_domain_name=null,"
                " network_tier=null}], ipv6_access_config=[],"
                " alias_ip_range=[]}],"
                " gke-a3-ultra-rdma-net.subnetwork_interfaces_gke))"
            ),
        },
        outputs=["instructions"],
    )
    tas_install_id = "topology-aware-scheduler-install"
    tas_install = DeploymentModule(
        id=tas_install_id,
        source="github.com/GoogleCloudPlatform/cluster-toolkit.git//community/modules/compute/gke-topology-scheduler?ref=e0c690b",
        use=[cluster_id],
    )
    workload_manager_install_id = "workload-manager-install"
    workload_manager_install = DeploymentModule(
        id=workload_manager_install_id,
        source="github.com/GoogleCloudPlatform/cluster-toolkit.git//modules/management/kubectl-apply?ref=e0c690b",
        use=[cluster_id],
        settings={
            "kueue": {"install": True, "version": "v0.9.1"},
            "jobset": {"install": True, "version": "v0.7.1"},
            "apply_manifests": [
                {"source": nccl_installer_path},
                {"source": mglru_disable_path},
            ],
        },
    )
    job_template_id = "job-template"
    job_template = DeploymentModule(
        id=job_template_id,
        source="modules/compute/gke-job-template",
        use=[gpu_pool_id],
        settings={
            "image": "nvidia/cuda:11.0.3-runtime-ubuntu20.04",
            "command": ["nvidia-smi"],
            "node_count": 2,
            "name": "run-nvidia-smi",
        },
        outputs=["instructions"],
    )

    primary_group = DeploymentGroup(
        group="primary",
        modules=[
            gpu_net_0,
            gpu_net_1,
            rma_net,
            a3_ultra_cluster,
            gpu_pool,
            tas_install,
            workload_manager_install,
            job_template,
        ],
    )
    a3_ultra_blueprint = Blueprint(
        blueprint_name=deployment_name,
        deployment_groups=[primary_group],
        vars=None,
    )

    blueprint_file_path = self._save_blueprint_to_file(
        deployment_name, a3_ultra_blueprint
    )
    blueprint_dependencies = ""
    return BlueprintGeneratorOutput(
        blueprint_file=blueprint_file_path,
        blueprint_dependencies=blueprint_dependencies,
    )


yaml.register_class(Blueprint)
yaml.register_class(DeploymentGroup)
yaml.register_class(DeploymentModule)
