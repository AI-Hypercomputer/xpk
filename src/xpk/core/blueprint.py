from typing import Any, AnyStr, Self, Optional
import yaml

blueprint_format = """bluprint_name: {name}
variables: {vars}
deployment_groups: 
{groups} 
"""

group_format = """id: {id}
group: {grop}
settings: {settings}
source: {source}
outputs: {outputs}
"""


class CtkDeploymentModule:

  def __init__(
      self,
      gid: str,
      source: str,
      settings: Optional[dict[str, Any]] = None,
      use: Optional[list[str]] = None,
      outputs: Optional[list[str]] = None,
  ):
    self.id = gid
    self.source = source
    self.settings = settings
    self.use = use
    self.outputs = outputs

  def __repr__(self) -> str:
    return group_format.format(
        id=self.id,
        group=self.id,
        settings=self.settings,
        source=self.source,
        outputs=self.outputs,
    )


network1 = CtkDeploymentModule(
    gid="network1",
    source="modules/network/vpc",
    settings={
        "subnetwork_name": "xpk-gke-a3-megagpu-subnet",
        "secondary_ranges": {
            "xpk-gke-a3-megagpu-subnet": [
                {"range_name": "pods", "ip_cidr_range": "10.4.0.0/14"},
                {"range_name": "services", "ip_cidr_range": "10.0.32.0/20"},
            ]
        },
    },
)
gpunets = CtkDeploymentModule(
    gid="gpunets",
    source="modules/network/multivpc",
    settings={
        "network_name_prefix": "xpk-deployment-subnet",
        "global_ip_address_range": "192.169.0.0/16",
        "network_count": 8,
        "subnetwork_cidr_suffix": 24,
    },
)

gke_cluster = CtkDeploymentModule(
    gid="gke_cluster",
    source=" modules/scheduler/gke-cluster",
    use=["network1", "gpunets"],
    settings={
        "master_authorized_networks": [{
            "cidr_block": (
                "$(vars.authorized_cidr)"
            ),  # Allows your machine run kubectl command. It's required for the multi-network setup.
            "display_name": "kubectl-access-network",
        }],
        "system_node_pool_machine_type": "e2-standard-32",
    },
)

group_placement_0 = CtkDeploymentModule(
    gid="group_placement_0",
    source="modules/compute/resource-policy",
    settings={
        "name": "$(vars.deployment_name)-gp-np-0",
        "group_placement_max_distance": 2,
    },
)

group_placement_1 = CtkDeploymentModule(
    gid="group_placement_1",
    source="modules/compute/resource-policy",
    use=["network1", "gpunets"],
    settings={
        "name": "$(vars.deployment_name)-gp-np-1",
        "group_placement_max_distance": 2,
    },
)

a3_megagpu_pool_0 = CtkDeploymentModule(
    gid="a3_megagpu_pool_0",
    source="modules/compute/gke-node-pool",
    use=["gke_cluster", "gpunets", "group_placement_0"],
    settings={
        "name": "a3-megagpu-pool-0",
        "machine_type": "a3-megagpu-8g",
        "autoscaling_total_min_nodes": 2,
        "initial_node_count": 2,
        "zones": "[$(vars.zone)]",
        "host_maintenance_interval": "PERIODIC",
    },
    outputs=["instructions"],
)

a3_megagpu_pool_1 = CtkDeploymentModule(
    gid="a3_megagpu_pool_1",
    source="modules/compute/gke-node-pool",
    use=["gke_cluster", "gpunets", "group_placement_1"],
    settings={
        "name": "a3-megagpu-pool-1",
        "machine_type": "a3-megagpu-8g",
        "autoscaling_total_min_nodes": 2,
        "initial_node_count": 2,
        "zones": "[$(vars.zone)]",
        "host_maintenance_interval": "PERIODIC",
    },
    outputs=["instructions"],
)

workload = CtkDeploymentModule(
    gid="workload_component_install",
    source="modules/management/kubectl-apply",
    use=["gke_cluster"],
    settings={
        "kueue": {
            "install": "true",
            "config_path": '$(ghpc_stage("xpk-gke-a3-megagpu-files"))/kueue-xpk-configuration.yaml.tftpl',
            "config_template_vars": {"num_chips": "32"},
        },
        "jobset": {"install": True},
    },
)

topology_scheduler = CtkDeploymentModule(
    gid="topology_aware_scheduler_install",
    source="community/modules/compute/gke-topology-scheduler",
    use=["gke_cluster"],
)

workload_configmap = CtkDeploymentModule(
    gid="workload_configmap",
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


class CtkBlueprint:
  """A class to represent Cluster Toolkit blueprint"""

  def __init__(self) -> None:
    self.deployment_groups = {}
    self.variables = {}
    self.blueprint_name = ""

  def __repr__(self) -> str:
    return blueprint_format.format(
        name=self.blueprint_name,
        vars=self.variables,
        groups=self.deployment_groups,
    )

  def save_to_file(self, fp: str) -> None:
    with open(fp, "w+") as outfile:
      yaml.dump(self, outfile, default_flow_style=False)

  def add_variable(self, key: str, val: str) -> None:
    self.variables[key] = val

  def add_deployment_module(
      self, group: str, module: CtkDeploymentModule
  ) -> None:
    # TODO raise exception and catch it if grup not defined in deployment_groups
    self.deployment_groups[group].append(module)

  def add_deployment_group(self, group: str):
    if group not in self.deployment_groups:
      self.deployment_groups[group] = []


def create_a3_mega_blueprint(
    project_id: str,
    deployment_name: str,
    region: str,
    zone: str,
    auth_cidr: str,
) -> str:
  """Create A3 mega blueprint and save it to file specified by filepath

  Args:
  Returns:
    - string represeting blueprint yaml
  """
  xpk_blueprint = CtkBlueprint()
  xpk_blueprint.blueprint_name = "xpk-gke-a3-megagpu"

  xpk_blueprint.add_variable("project_id", project_id)
  xpk_blueprint.add_variable("deployment_name", deployment_name)
  xpk_blueprint.add_variable("region", region)
  xpk_blueprint.add_variable("zone", zone)
  xpk_blueprint.add_variable("authorized_cid", auth_cidr)

  group = "primary"
  xpk_blueprint.add_deployment_group(group)

  xpk_blueprint.add_deployment_module(group, network1)
  xpk_blueprint.add_deployment_module(group, gpunets)
  xpk_blueprint.add_deployment_module(group, gke_cluster)
  xpk_blueprint.add_deployment_module(group, group_placement_0)
  xpk_blueprint.add_deployment_module(group, group_placement_1)
  xpk_blueprint.add_deployment_module(group, a3_megagpu_pool_0)
  xpk_blueprint.add_deployment_module(group, a3_megagpu_pool_1)
  xpk_blueprint.add_deployment_module(group, workload)
  xpk_blueprint.add_deployment_module(group, topology_scheduler)
  xpk_blueprint.add_deployment_module(group, workload_configmap)

  return yaml.dump(xpk_blueprint)
