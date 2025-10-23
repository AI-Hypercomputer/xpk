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
import textwrap
from dataclasses import dataclass
from typing import Optional, List, Dict, Any
import json
from jinja2 import Environment, FileSystemLoader
from ..utils.execution_context import is_dry_run
from ..utils.kueue import is_queued_cluster

from .capacity import B200_DEVICE_TYPE, H100_MEGA_DEVICE_TYPE, H200_DEVICE_TYPE
from .scheduling import (
    create_accelerator_label,
    create_machine_label,
)
from .system_characteristics import (
    AcceleratorTypeToAcceleratorCharacteristics,
    SystemCharacteristics,
)
from ..core.commands import (
    run_command_for_value,
    run_command_with_updates,
    run_command_with_updates_retry,
)
from ..utils.file import write_tmp_file
from ..utils.console import xpk_print, xpk_exit
from ..utils.templates import TEMPLATE_PATH, get_templates_absolute_path

WAIT_FOR_KUEUE_TIMEOUT = "10m"
CLUSTER_QUEUE_NAME = "cluster-queue"
LOCAL_QUEUE_NAME = "multislice-queue"
SUB_SLICE_TOPOLOGY_NAME = "sub-slice-topology"
KUEUE_CONFIG_JINJA_FILE = "kueue_config.yaml.j2"
KUEUE_GKE_DEFAULT_TOPOLOGY_JINJA_FILE = "kueue_gke_default_topology.yaml.j2"
KUEUE_CONTROLLER_MANAGER_JINJA_FILE = "kueue_controller_manager.yaml.j2"
KUEUE_SUB_SLICING_TOPOLOGY_JINJA_FILE = "kueue_sub_slicing_topology.yaml.j2"
MEMORY_SIZE_PER_VM = 1.2
MIN_MEMORY_LIMIT_SIZE = 4096
KUEUE_VERSION = "v0.14.1"


@dataclass
class KueueConfig:
  system: SystemCharacteristics
  total_chips: int
  cpu_limit: int
  memory_limit: str
  configure_sub_slicing: bool
  is_pathways_cluster: bool = False
  autoprovisioning_enabled: bool = False
  flex: bool = False
  num_slices: int = 1


@dataclass
class _NameAndYaml:
  name: str
  yaml: str


class KueueManager:
  """Manages the installation and configuration of Kueue on an XPK cluster."""

  def __init__(
      self,
      kueue_version: str = KUEUE_VERSION,
      template_path=TEMPLATE_PATH,
  ):
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
    return_code, installed_version = self.get_installed_kueue_version()

    if return_code == 0:
      if installed_version and installed_version > self.kueue_version:
        xpk_print(
            f"Cluster has a newer Kueue version, {installed_version}. Skipping"
            " installation."
        )
        return 0
      else:
        xpk_print(f"Upgrading Kueue to version {self.kueue_version}...")
    else:
      xpk_print(f"Installing Kueue version {self.kueue_version}...")

    install_return_code = self.__install(tolerations)
    if install_return_code != 0:
      return install_return_code

    return self.__configure(kueue_config)

  def get_installed_kueue_version(self) -> tuple[int, str | None]:
    command = (
        "kubectl get deployment kueue-controller-manager -n kueue-system -o"
        " jsonpath='{.spec.template.spec.containers[0].image}'"
    )
    task = "Get kueue version on server"
    return_code, val = run_command_for_value(
        command,
        task,
        dry_run_return_val="""
        v0.14.1""",
    )
    if return_code != 0:
      return return_code, None
    version_tag = val.split(":")
    if len(version_tag) == 1:
      return 1, None
    return return_code, version_tag[-1]

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

  def __install_kueue_crs(self) -> int:
    manifest_url = f"https://github.com/kubernetes-sigs/kueue/releases/download/{self.kueue_version}/manifests.yaml"
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
        "kubectl wait deploy/kueue-controller-manager -nkueue-system"
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
        kueue_config.system, kueue_config.configure_sub_slicing
    )
    topology_name = (
        topology_name_and_yaml.name if topology_name_and_yaml else None
    )

    # The manager builds the context internally based on its opinionated logic
    context = self.__build_template_context(
        system=kueue_config.system,
        total_chips=kueue_config.total_chips,
        is_pathways=kueue_config.is_pathways_cluster,
        autoprovisioning=kueue_config.autoprovisioning_enabled,
        flex=kueue_config.flex,
        num_slices=kueue_config.num_slices,
        cpu_limit=kueue_config.cpu_limit,
        memory_limit=kueue_config.memory_limit,
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
    accelerator_label = create_accelerator_label(
        system.accelerator_type, system
    )
    if accelerator_label:
      key, value = accelerator_label.split(":", 1)
      node_labels_dict[key] = value.strip()

    machine_label = create_machine_label(
        system.accelerator_type, system, autoprovisioning
    )
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

    if flex and is_queued_cluster(num_slices):
      admission_checks = textwrap.dedent("""
        admissionChecks:
        - dws-prov
      """)
    else:
      admission_checks = ""

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
      self, system: SystemCharacteristics, configure_sub_slicing: bool
  ) -> _NameAndYaml | None:
    if system.device_type in [
        H100_MEGA_DEVICE_TYPE,
        H200_DEVICE_TYPE,
        B200_DEVICE_TYPE,
    ]:
      return _NameAndYaml(
          name="gke-default",
          yaml=self.template_env.get_template(
              KUEUE_GKE_DEFAULT_TOPOLOGY_JINJA_FILE
          ).render(),
      )
    elif configure_sub_slicing:
      return _NameAndYaml(
          name=SUB_SLICE_TOPOLOGY_NAME,
          yaml=self.template_env.get_template(
              KUEUE_SUB_SLICING_TOPOLOGY_JINJA_FILE
          ).render({
              "sub_slice_topology_name": SUB_SLICE_TOPOLOGY_NAME,
          }),
      )
    else:
      return None

  def __apply_manifest(self, manifest: str) -> int:
    task = "Applying Kueue Custom Resources"
    if is_dry_run():
      xpk_print(f"Applying following Kueue resources:{manifest}")
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
