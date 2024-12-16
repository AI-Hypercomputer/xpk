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

from .blueprint import CtkBlueprint, CtkDeploymentGroup, CtkDeploymentModule


def create_a3_ultra_blueprint(
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
) -> CtkBlueprint:
  """Create A3 ultra blueprint.

  Args:
  Returns:
    - CtkBlueprint representing cluster toolkit blueprint
  """
  nccl_installer_path = '$(ghpc_stage("./nccl-installer.yaml"))'
  mglru_disable_path = '$(ghpc_stage("./mglru-disable.yaml"))'
  net_0_id = "gke-a3-ultra-net-0"
  gpu_net_0 = CtkDeploymentModule(
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
  gpu_net_1 = CtkDeploymentModule(
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
  rma_net = CtkDeploymentModule(
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
  a3_ultra_cluster = CtkDeploymentModule(
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
  gpu_pool = CtkDeploymentModule(
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
  tas_install = CtkDeploymentModule(
      id=tas_install_id,
      source="github.com/GoogleCloudPlatform/cluster-toolkit.git//community/modules/compute/gke-topology-scheduler?ref=e0c690b",
      use=[cluster_id],
  )
  workload_manager_install_id = "workload-manager-install"
  workload_manager_install = CtkDeploymentModule(
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
  job_template = CtkDeploymentModule(
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

  primary_group = CtkDeploymentGroup(
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
  xpk_blueprint = CtkBlueprint(
      blueprint_name=deployment_name,
      deployment_groups=[primary_group],
      vars=None,
  )

  return xpk_blueprint
