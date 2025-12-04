"""
Copyright 2025 Google LLC

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

import math
from dataclasses import dataclass
from typing import Optional, List, Dict, Any
import json
from jinja2 import Environment, FileSystemLoader

from ..utils.topology import get_slice_topology_level, get_topology_product, is_topology_contained
from ..utils.kueue import is_queued_cluster
from kubernetes.utils import parse_quantity
from .system_characteristics import (
    SUB_SLICING_TOPOLOGIES,
    AcceleratorType,
    AcceleratorTypeToAcceleratorCharacteristics,
    SystemCharacteristics,
    create_accelerator_label,
    create_machine_label,
)
from ..core.commands import (
    run_command_for_value,
    run_command_with_updates,
    run_command_with_updates_retry,
)
from ..utils.file import write_tmp_file
from ..utils.console import xpk_print, xpk_exit, ask_for_user_consent
from ..utils.templates import TEMPLATE_PATH, get_templates_absolute_path
from packaging.version import Version

KUEUE_VERSION = Version("v0.14.3")
LATEST_BREAKING_VERSION = Version("v0.14.0")
WAIT_FOR_KUEUE_TIMEOUT = "10m"
CLUSTER_QUEUE_NAME = "cluster-queue"
LOCAL_QUEUE_NAME = "multislice-queue"
SUB_SLICE_TOPOLOGY_NAME = "sub-slice-topology"
SUPER_SLICE_TOPOLOGY_NAME = "super-slice-topology"
KUEUE_CONFIG_JINJA_FILE = "kueue_config.yaml.j2"
KUEUE_GKE_DEFAULT_TOPOLOGY_JINJA_FILE = "kueue_gke_default_topology.yaml.j2"
KUEUE_CONTROLLER_MANAGER_JINJA_FILE = "kueue_controller_manager.yaml.j2"
KUEUE_SUB_SLICING_TOPOLOGY_JINJA_FILE = "kueue_sub_slicing_topology.yaml.j2"
KUEUE_SUPER_SLICING_TOPOLOGY_JINJA_FILE = "kueue_super_slicing_topology.yaml.j2"
MEMORY_SIZE_PER_VM = 1.2
MIN_MEMORY_LIMIT_SIZE = 4096


@dataclass(frozen=True)
class KueueConfig:
  system: SystemCharacteristics
  total_chips: int
  cpu_limit: int
  memory_limit: str
  configure_sub_slicing: bool
  configure_super_slicing: bool
  is_pathways_cluster: bool = False
  autoprovisioning_enabled: bool = False
  flex: bool = False
  num_slices: int = 1


@dataclass(frozen=True)
class _NameAndYaml:
  name: str
  yaml: str


class KueueManager:
  """Manages the installation and configuration of Kueue on an XPK cluster."""

  def __init__(
      self,
      project: str,
      zone: str,
      kueue_version: Version = KUEUE_VERSION,
      template_path=TEMPLATE_PATH,
  ):
    self.project = project
    self.zone = zone
    self.kueue_version = kueue_version

    self.template_env = Environment(
        loader=FileSystemLoader(
            searchpath=get_templates_absolute_path(template_path)
        )
    )

  def install_or_upgrade(
      self,
      kueue_config: KueueConfig,
      tolerations: Optional[List[Dict[str, Any]]] = None,
  ) -> int:
    """
    Ensures the correct version of Kueue is installed. Upgrades if the installed
    version is older or non-existent.

    Args:
        tolerations: An optional list of tolerations to apply to the kueue-controller-manager.
    """
    return_code, installed_version = get_installed_kueue_version()

    if return_code == 0 and installed_version:
      if installed_version > self.kueue_version:
        xpk_print(
            f"Cluster has a newer Kueue version, {installed_version}. Skipping"
            " installation."
        )
        return 0
      else:
        xpk_print(f"Upgrading Kueue to version v{self.kueue_version}...")
        assert installed_version
        prepare_code = self.__prepare_for_upgrade(installed_version)
        if prepare_code != 0:
          return prepare_code
    else:
      xpk_print(f"Installing Kueue version v{self.kueue_version}...")

    install_return_code = self.__install(tolerations)
    if install_return_code != 0:
      return install_return_code

    return self.__configure(kueue_config)

  def __install(
      self,
      tolerations: Optional[List[Dict[str, Any]]] = None,
  ) -> int:
    """
    Installs Kueue from the official manifest and then applies any necessary patches.

    Args:
        tolerations: An optional list of tolerations to apply to the kueue-controller-manager.
    """
    return_code = self.__install_kueue_crs()
    if return_code != 0:
      return return_code

    if tolerations:
      return_code = self.__patch_tolerations(tolerations)
      if return_code != 0:
        return return_code

    return self.__wait_for_kueue_available()

  def __prepare_for_upgrade(self, installed_version: Version) -> int:
    if installed_version >= LATEST_BREAKING_VERSION:
      return 0

    xpk_print(
        f"Currently installed Kueue version v{installed_version} is"
        f" incompatible with the newer v{self.kueue_version}."
    )

    changelog_link = f"https://github.com/kubernetes-sigs/kueue/blob/main/CHANGELOG/CHANGELOG-{self.kueue_version.major}.{self.kueue_version.minor}.md"
    agreed = ask_for_user_consent(
        "Do you want to allow XPK to update Kueue automatically? This will"
        " delete all existing Kueue resources and create new ones. If you"
        " decline, you will need to upgrade the Kueue manually (see"
        f" {changelog_link} for help)."
    )
    if not agreed:
      return 1

    return self.__delete_all_kueue_resources()

  def __delete_all_kueue_resources(self) -> int:
    return_code, kueue_crds_string = run_command_for_value(
        "kubectl get crd -o name | grep .kueue.x-k8s.io", "Get Kueue CRDs"
    )
    if return_code != 0:
      return return_code

    kueue_crds = [
        line.strip().removeprefix(
            "customresourcedefinition.apiextensions.k8s.io/"
        )
        for line in kueue_crds_string.strip().split("\n")
    ]

    for crd in kueue_crds:
      return_code = run_command_with_updates(
          f"kubectl delete {crd} --all", f"Delete all resources of type {crd}"
      )
      if return_code != 0:
        return return_code

    for crd in kueue_crds:
      return_code = run_command_with_updates(
          f"kubectl delete crd {crd}", f"Delete CRD {crd}"
      )
      if return_code != 0:
        return return_code

    return run_command_with_updates(
        "kubectl delete deployment kueue-controller-manager -n kueue-system",
        "Delete Kueue Controller Manager deployment",
    )

  def __install_kueue_crs(self) -> int:
    manifest_url = f"https://github.com/kubernetes-sigs/kueue/releases/download/v{self.kueue_version}/manifests.yaml"
    install_command = (
        f"kubectl apply --server-side --force-conflicts -f {manifest_url}"
    )
    task = "Installing Kueue Custom Resources"
    return_code = run_command_with_updates_retry(
        install_command, "Install Kueue"
    )
    if return_code != 0:
      xpk_print(f"{task} returned ERROR {return_code}")
    return return_code

  def __patch_tolerations(self, tolerations: List[Dict[str, Any]]) -> int:
    patch = {"spec": {"template": {"spec": {"tolerations": tolerations}}}}
    patch_str = json.dumps(patch)
    patch_command = (
        "kubectl patch deployment kueue-controller-manager -n kueue-system"
        f" --type='strategic' --patch='{patch_str}'"
    )
    task = "Patch Kueue Tolerations"
    return_code = run_command_with_updates_retry(
        patch_command, "Patch Kueue Tolerations"
    )
    if return_code != 0:
      xpk_print(f"{task} returned ERROR {return_code}")
    return return_code

  def __wait_for_kueue_available(self) -> int:
    """Wait for Kueue to be fully available.

    Args:
      args: user provided arguments for running the command.

    Returns:
      0 if successful and 1 otherwise.
    """
    command = (
        "kubectl wait deploy/kueue-controller-manager -n kueue-system"
        f" --for=condition=available --timeout={WAIT_FOR_KUEUE_TIMEOUT}"
    )
    task = "Wait for Kueue to be available"
    return_code = run_command_with_updates(command, task)
    if return_code != 0:
      xpk_print(f"{task} returned ERROR {return_code}")
    return return_code

  def __configure(
      self,
      kueue_config: KueueConfig,
  ) -> int:
    """
    Configures Kueue with opinionated defaults for XPK.

    Args:
        kueue_config: The KueueConfig object containing all configuration parameters.
    Returns:
        0 if successful and 1 otherwise.
    """
    template = self.template_env.get_template(KUEUE_CONFIG_JINJA_FILE)

    topology_name_and_yaml = self.__get_topology_name_and_yaml(
        kueue_config.system,
        kueue_config.configure_sub_slicing,
        kueue_config.configure_super_slicing,
    )
    topology_name = (
        topology_name_and_yaml.name if topology_name_and_yaml else None
    )
    cpu_limit, memory_limit = self.__autocorrect_resource_limits(kueue_config)

    # The manager builds the context internally based on its opinionated logic
    context = self.__build_template_context(
        system=kueue_config.system,
        total_chips=kueue_config.total_chips,
        is_pathways=kueue_config.is_pathways_cluster,
        autoprovisioning=kueue_config.autoprovisioning_enabled,
        flex=kueue_config.flex,
        num_slices=kueue_config.num_slices,
        cpu_limit=cpu_limit,
        memory_limit=memory_limit,
        topology_name=topology_name,
    )

    config_yaml = template.render(context)
    yamls = [config_yaml]

    if topology_name_and_yaml:
      yamls.append(topology_name_and_yaml.yaml)

    rendered_manifest = "\n---\n".join(yamls)
    return_code = self.__apply_manifest(rendered_manifest)
    if return_code != 0:
      return return_code

    return self.__update_kueue_resources_if_necessary()

  def __build_template_context(
      self,
      system: SystemCharacteristics,
      total_chips: int,
      is_pathways: bool,
      autoprovisioning: bool,
      flex: bool,
      num_slices: int,
      cpu_limit: int,
      memory_limit: str,
      topology_name: str | None,
  ) -> Dict[str, Any]:
    """Prepares the context for the Jinja2 template."""
    # Main accelerator flavor
    device_type_str = system.device_type.replace("_", "-")
    main_flavor_name = f"{num_slices}x{device_type_str}"

    node_labels_dict = {}
    accelerator_label = create_accelerator_label(system)
    if accelerator_label:
      key, value = accelerator_label.split(":", 1)
      node_labels_dict[key] = value.strip()

    if system.supports_super_slicing:
      node_labels_dict["cloud.google.com/gke-tpu-partition-4x4x4-state"] = (
          "HEALTHY"
      )
    elif not autoprovisioning:
      machine_label = create_machine_label(system)
      if machine_label:
        key, value = machine_label.split(":", 1)
        node_labels_dict[key] = value.strip()

    topology_label = f"topologyName: {topology_name}" if topology_name else ""

    flavors = [{
        "name": main_flavor_name,
        "nodeLabels": node_labels_dict,
        "topologyLabel": topology_label,
    }]

    managed_resource = AcceleratorTypeToAcceleratorCharacteristics[
        system.accelerator_type
    ].resource_type

    covered_resources = [managed_resource]
    resources = [{"name": managed_resource, "nominalQuota": total_chips}]

    if cpu_limit:
      covered_resources.append("cpu")
      resources.append({"name": "cpu", "nominalQuota": cpu_limit})
    if memory_limit:
      covered_resources.append("memory")
      resources.append({"name": "memory", "nominalQuota": memory_limit})

    resource_groups = [{
        "coveredResources": covered_resources,
        "flavors": [{"name": main_flavor_name, "resources": resources}],
    }]

    # Add Pathway-specific resources if needed
    if is_pathways:
      flavors.append({
          "name": "cpu-user",
          "nodeLabels": {"cloud.google.com/gke-nodepool": "cpu-np"},
      })
      resource_groups.append({
          "coveredResources": ["cpu", "memory"],
          "flavors": [{
              "name": "cpu-user",
              "resources": [
                  {"name": "cpu", "nominalQuota": 480},
                  {"name": "memory", "nominalQuota": "2000G"},
              ],
          }],
      })

    admission_checks = []
    if system.supports_super_slicing:
      admission_checks.append("ss-kueue-operator")
    if flex and is_queued_cluster(num_slices, system.accelerator_type):
      admission_checks.append("dws-prov")

    return {
        "flavors": flavors,
        "resource_groups": resource_groups,
        "autoprovisioning_enabled": autoprovisioning,
        "managed_resource": managed_resource,
        "cluster_queue_name": CLUSTER_QUEUE_NAME,
        "local_queue_name": LOCAL_QUEUE_NAME,
        "admission_checks": admission_checks,
    }

  def __get_topology_name_and_yaml(
      self,
      system: SystemCharacteristics,
      configure_sub_slicing: bool,
      configure_super_slicing: bool,
  ) -> _NameAndYaml | None:
    if (
        system.accelerator_type == AcceleratorType["GPU"]
        and system.gpu_requires_topology
    ):
      return _NameAndYaml(
          name="gke-default",
          yaml=self.template_env.get_template(
              KUEUE_GKE_DEFAULT_TOPOLOGY_JINJA_FILE
          ).render(),
      )
    elif configure_sub_slicing:
      sorted_topologies = sorted(
          SUB_SLICING_TOPOLOGIES, key=get_topology_product, reverse=True
      )
      levels = [
          get_slice_topology_level(topology)
          for topology in sorted_topologies
          if is_topology_contained(
              contained=topology, container=system.topology
          )
      ]
      levels.append("kubernetes.io/hostname")

      return _NameAndYaml(
          name=SUB_SLICE_TOPOLOGY_NAME,
          yaml=self.template_env.get_template(
              KUEUE_SUB_SLICING_TOPOLOGY_JINJA_FILE
          ).render({
              "sub_slice_topology_name": SUB_SLICE_TOPOLOGY_NAME,
              "levels": levels,
          }),
      )
    elif configure_super_slicing:
      return _NameAndYaml(
          name=SUPER_SLICE_TOPOLOGY_NAME,
          yaml=self.template_env.get_template(
              KUEUE_SUPER_SLICING_TOPOLOGY_JINJA_FILE
          ).render({
              "super_slice_topology_name": SUPER_SLICE_TOPOLOGY_NAME,
          }),
      )
    else:
      return None

  def __apply_manifest(self, manifest: str) -> int:
    task = "Applying Kueue Custom Resources"
    tmp_file = write_tmp_file(manifest)
    command = f"kubectl apply -f {tmp_file}"
    return run_command_with_updates(command, task)

  def __update_kueue_resources_if_necessary(self) -> int:
    """Patch memory size limit if necessary."""
    # Get total number of nodes
    cmd_total_node_num = "kubectl get node --no-headers | wc -l"
    return_code, out = run_command_for_value(
        cmd_total_node_num, "Count total nodes"
    )
    if return_code != 0:
      xpk_exit(1)
    # 1.2MiB per VM or 4GiB (whichever is greater).
    new_memory_limit = (
        f"{max(math.ceil(int(out) * MEMORY_SIZE_PER_VM), MIN_MEMORY_LIMIT_SIZE)}Mi"
    )
    patch = {
        "spec": {
            "template": {
                "spec": {
                    "containers": [{
                        "name": "manager",
                        "resources": {"limits": {"memory": new_memory_limit}},
                    }]
                }
            }
        }
    }
    patch_str = json.dumps(patch)
    patch_command = (
        "kubectl patch deployment kueue-controller-manager -n kueue-system"
        f" --type='strategic' --patch='{patch_str}'"
    )
    task = "Updating Kueue Controller Manager resources"
    return_code = run_command_with_updates_retry(
        patch_command,
        task,
    )
    if return_code != 0:
      xpk_print(f"{task} returned ERROR {return_code}")
    return return_code

  def __autocorrect_resource_limits(
      self, kueue_config: KueueConfig
  ) -> tuple[int, str]:
    """Verify specified CPU and memory limits against machine type."""

    cpu_limit = kueue_config.cpu_limit
    memory_limit_str = kueue_config.memory_limit
    if not cpu_limit and not memory_limit_str:
      return cpu_limit, memory_limit_str

    # Get CPU and memory capacity from machine type
    command = (
        "gcloud compute machine-types describe"
        f" {kueue_config.system.gce_machine_type} "
        f" --project={self.project} --zone={self.zone}"
        " --format='value(guestCpus,memoryMb)'"
    )
    return_code, out = run_command_for_value(
        command,
        "Get vCPU and memory capacity for machine type",
        dry_run_return_val="10 10",
    )
    if return_code != 0:
      xpk_print(
          "Unable to verify vCPU and memory capacity for machine type."
          " XPK will proceed with using user-defined  limits."
      )
      return cpu_limit, memory_limit_str

    cpu_capacity_str, memory_capacity_MB_str = out.split()
    if cpu_limit:
      cpu_limit = _autocorrect_cpu_limit(cpu_limit, int(cpu_capacity_str))
    if memory_limit_str:
      memory_limit_str = _autocorrect_memory_limit(
          memory_limit_str, memory_capacity_MB_str
      )
    return cpu_limit, memory_limit_str


def get_installed_kueue_version(
    dry_run_version: Version | None = None,
) -> tuple[int, Version | None]:
  command = (
      "kubectl get deployment kueue-controller-manager -n kueue-system -o"
      " jsonpath='{.spec.template.spec.containers[0].image}'"
  )
  task = "Get kueue version on server"
  return_code, val = run_command_for_value(
      command,
      task,
      dry_run_return_val=(
          f"registry.k8s.io/kueue/kueue:v{dry_run_version}"
          if dry_run_version
          else ""
      ),
  )
  if return_code != 0:
    return return_code, None
  version_tag = val.split(":")
  if len(version_tag) == 1:
    return 1, None
  return return_code, Version(version_tag[-1])


def has_sub_slicing_enabled() -> tuple[int, bool | None]:
  return_code, value = run_command_for_value(
      command="kubectl get topology",
      task="Get defined topologies",
      dry_run_return_val=SUB_SLICE_TOPOLOGY_NAME,
  )

  if return_code != 0:
    return return_code, None

  return return_code, SUB_SLICE_TOPOLOGY_NAME in value


def has_super_slicing_enabled() -> tuple[int, bool | None]:
  return_code, value = run_command_for_value(
      command="kubectl get topology",
      task="Get defined topologies",
      dry_run_return_val=SUPER_SLICE_TOPOLOGY_NAME,
  )

  if return_code != 0:
    return return_code, None

  return return_code, SUPER_SLICE_TOPOLOGY_NAME in value


def _autocorrect_cpu_limit(cpu_limit: int, cpu_capacity: int) -> int:
  if cpu_limit > cpu_capacity:
    xpk_print(
        "The CPU limit is above the available capacity."
        f" We will set CPU limit to {cpu_capacity}."
    )
  elif cpu_limit < cpu_capacity:
    xpk_print(
        "The CPU limit is below the available capacity, which would lead"
        f" to underutilization. We will set CPU limit to {cpu_capacity}."
    )
  return cpu_capacity


def _autocorrect_memory_limit(
    memory_limit_str: str, memory_capacity_MB_str: str
) -> str:
  memory_limit_bytes = parse_quantity(memory_limit_str)
  memory_capacity_bytes = int(memory_capacity_MB_str) << 20
  if memory_limit_bytes == memory_capacity_bytes:
    return memory_limit_str
  memory_limit_str = memory_capacity_MB_str + "Mi"
  if memory_limit_bytes > memory_capacity_bytes:
    xpk_print(
        "The memory limit is above the available capacity. We will set"
        f" memory limit to {memory_limit_str}."
    )
  else:
    xpk_print(
        "The memory limit is below the available capacity, which would"
        " lead to underutilization. We will set the memory limit to"
        f" {memory_limit_str}."
    )
  return memory_limit_str
