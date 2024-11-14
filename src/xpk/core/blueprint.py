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
from typing import Any, Optional
import ruamel.yaml

yaml = ruamel.yaml.YAML()


@dataclass
class CtkDeploymentModule:
  """CtkDeploymentModule represents cluster toolkit deployment module

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
class CtkDeploymentGroup:
  """CtkDeploymentGroup represents cluster toolkit deployment group

  Attributes:
    group (str): deployment group name
    modules (list[CtkDeploymentModule]): deployments modules
  """

  modules: list[CtkDeploymentModule]
  group: Optional[str]


@dataclass
class CtkBlueprint:
  """A class to represent Cluster Toolkit blueprint"""

  vars: dict[str, str]
  deployment_groups: list[CtkDeploymentGroup]
  blueprint_name: Optional[str]


yaml.register_class(CtkBlueprint)
yaml.register_class(CtkDeploymentGroup)
yaml.register_class(CtkDeploymentModule)


def create_a3_mega_blueprint(
    project_id: str,
    deployment_name: str,
    region: str,
    zone: str,
    auth_cidr: str,
    num_nodes: int = 2,
    pods_ip_cidr_range: str = "10.4.0.0/14",
    services_ip_cidr_range: str = "10.0.32.0/20",
    global_ip_address_range: str = "192.169.0.0/16",
    system_node_pool_machine_type: str = "e2-standard-32",
    num_chips: int = 32,
) -> CtkBlueprint:
  """Create A3 mega blueprint and save it to file specified by filepath

  Args:
  Returns:
    - CtkBlueprint representing cluter toolkit blueprint
  """

  network1 = CtkDeploymentModule(
      id="network1",
      source="modules/network/vpc",
      settings={
          "subnetwork_name": "xpk-gke-a3-megagpu-subnet",
          "secondary_ranges": {
              "xpk-gke-a3-megagpu-subnet": [
                  {"range_name": "pods", "ip_cidr_range": pods_ip_cidr_range},
                  {
                      "range_name": "services",
                      "ip_cidr_range": services_ip_cidr_range,
                  },
              ]
          },
      },
  )
  gpunets = CtkDeploymentModule(
      id="gpunets",
      source="modules/network/multivpc",
      settings={
          "network_name_prefix": f"{deployment_name}-gpunet",
          "global_ip_address_range": global_ip_address_range,
          "network_count": 8,
          "subnetwork_cidr_suffix": 24,
      },
  )

  gke_cluster = CtkDeploymentModule(
      id="gke_cluster",
      source="modules/scheduler/gke-cluster",
      use=["network1", "gpunets"],
      settings={
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

  group_placement_0 = CtkDeploymentModule(
      id="group_placement_0",
      source="modules/compute/resource-policy",
      settings={
          "name": f"{deployment_name}-gp-np-0",
          "group_placement_max_distance": 2,
      },
  )

  group_placement_1 = CtkDeploymentModule(
      id="group_placement_1",
      source="modules/compute/resource-policy",
      settings={
          "name": f"{deployment_name}-gp-np-1",
          "group_placement_max_distance": 2,
      },
  )

  a3_megagpu_pool_0 = CtkDeploymentModule(
      id="a3_megagpu_pool_0",
      source="modules/compute/gke-node-pool",
      use=["gke_cluster", "gpunets", "group_placement_0"],
      settings={
          "name": "a3-megagpu-pool-0",
          "machine_type": "a3-megagpu-8g",
          "autoscaling_total_min_nodes": 2,
          "initial_node_count": num_nodes,
          "zones": [zone],
          "host_maintenance_interval": "PERIODIC",
      },
      outputs=["instructions"],
  )

  a3_megagpu_pool_1 = CtkDeploymentModule(
      id="a3_megagpu_pool_1",
      source="modules/compute/gke-node-pool",
      use=["gke_cluster", "gpunets", "group_placement_1"],
      settings={
          "name": "a3-megagpu-pool-1",
          "machine_type": "a3-megagpu-8g",
          "autoscaling_total_min_nodes": 2,
          "initial_node_count": num_nodes,
          "zones": [zone],
          "host_maintenance_interval": "PERIODIC",
      },
      outputs=["instructions"],
  )

  workload = CtkDeploymentModule(
      id="workload_component_install",
      source="modules/management/kubectl-apply",
      use=["gke_cluster"],
      settings={
          "kueue": {
              "install": True,
              "config_path": '$(ghpc_stage("xpk-gke-a3-megagpu-files"))/kueue-xpk-configuration.yaml.tftpl',
              "config_template_vars": {"num_chips": f"{num_chips}"},
          },
          "jobset": {"install": True},
      },
  )

  topology_scheduler = CtkDeploymentModule(
      id="topology_aware_scheduler_install",
      source="community/modules/compute/gke-topology-scheduler",
      use=["gke_cluster"],
  )

  workload_configmap = CtkDeploymentModule(
      id="workload_configmap",
      source="modules/management/kubectl-apply",
      use=["gke_cluster"],
      settings={
          "apply_manifests": [{
              "source": '$(ghpc_stage("xpk-gke-a3-megagpu-files"))/config-map.yaml.tftpl',
              "template_vars": {
                  "name": "xpk-gke-a3-megagpu-resources-configmap",
                  "num_nodes": "4",
              },
          }]
      },
  )
  primary_group = CtkDeploymentGroup(
      group="primary",
      modules=[
          network1,
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
  xpk_blueprint = CtkBlueprint(
      blueprint_name="xpk-gke-a3-megagpu",
      deployment_groups=[primary_group],
      vars={
          "project_id": project_id,
          "deployment_name": deployment_name,
          "region": region,
          "zone": zone,
          "authorized_cidr": auth_cidr,
      },
  )

  return xpk_blueprint
