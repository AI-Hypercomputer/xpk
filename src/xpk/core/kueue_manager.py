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
from argparse import Namespace
from dataclasses import dataclass
from typing import Optional, List, Dict, Any
import json
from jinja2 import Environment, FileSystemLoader

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

WAIT_FOR_KUEUE_TIMEOUT = "10m"
CLUSTER_QUEUE_NAME = "cluster-queue"
LOCAL_QUEUE_NAME = "multislice-queue"
KUEUE_CONFIG_JINJA_FILE = "kueue_config.yaml.j2"
KUEUE_TOPOLOGY_JINJA_FILE = "kueue_topology.yaml.j2"
KUEUE_CONTROLLER_MANAGER_JINJA_FILE = "kueue_controller_manager.yaml.j2"
MEMORY_SIZE_PER_VM = 1.2
MIN_MEMORY_LIMIT_SIZE = 4096


@dataclass
class KueueConfig:
  system: SystemCharacteristics
  total_chips: int
  is_pathways_cluster: bool = False
  autoprovisioning_enabled: bool = False
  cpu_quota: int = 10000
  memory_quota: str = "10000Gi"
  flex: bool = False
  num_slices: int = 1


class KueueManager:
  """Manages the installation and configuration of Kueue on an XPK cluster."""

  def __init__(self, kueue_version: str = "v0.12.2"):
    self.kueue_version = kueue_version
    self.template_env = Environment(
        loader=FileSystemLoader("src/xpk/templates/")
    )

  def install_or_upgrade(
      self,
      kueue_config: KueueConfig,
      tolerations: Optional[List[Dict[str, Any]]] = None,
      dry_run: bool = False,
  ) -> int:
    """
    Ensures the correct version of Kueue is installed. Upgrades if the installed
    version is older or non-existent.

    Args:
        tolerations: An optional list of tolerations to apply to the kueue-controller-manager.
        dry_run: If true, the command will not actually be executed.
    """
    # Step 1: Install directly from the official URL
    return_code, installed_version = self._get_installed_kueue_version(dry_run)

    if return_code == 0 and installed_version >= self.kueue_version:
      print(
          f"Kueue version {installed_version} is already up to date. Skipping"
          " installation."
      )
      return 0

    print(f"Installing/Upgrading Kueue to version {self.kueue_version}...")

    install_return_code = self._install(tolerations, dry_run)
    if install_return_code != 0:
      return install_return_code

    return self._configure(kueue_config, dry_run)

  def _get_installed_kueue_version(
      self, dry_run: bool = False
  ) -> tuple[int, str]:
    command = "kubectl kueue version"
    task = "Get kueue version on server"
    return_code, val = run_command_for_value(
        command,
        task,
        Namespace(dry_run=dry_run),
        dry_run_return_val="""
        v0.12.1""",
    )
    if return_code != 0:
      return return_code, ""
    lines = val.splitlines()
    if len(lines) == 1:
      return 1, ""
    server_version_line = lines[1]
    manager_image_version = server_version_line.split(":")[-1]
    return return_code, manager_image_version

  def _install(
      self,
      tolerations: Optional[List[Dict[str, Any]]] = None,
      dry_run: bool = False,
  ) -> int:
    """
    Installs Kueue from the official manifest and then applies any necessary patches.

    Args:
        tolerations: An optional list of tolerations to apply to the kueue-controller-manager.
        dry_run: If true, the command will not actually be executed.
    """
    # Step 1: Install directly from the official URL
    manifest_url = f"https://github.com/kubernetes-sigs/kueue/releases/download/{self.kueue_version}/manifests.yaml"
    install_command = (
        f"kubectl apply --server-side --force-conflicts -f {manifest_url}"
    )
    return_code = run_command_with_updates_retry(
        install_command, "Install Kueue", Namespace(dry_run=dry_run)
    )
    if return_code != 0:
      return return_code

    # Step 2: Patch the deployment if tolerations are provided
    if tolerations:
      patch = {"spec": {"template": {"spec": {"tolerations": tolerations}}}}
      patch_str = json.dumps(patch)
      patch_command = (
          "kubectl patch deployment kueue-controller-manager -n kueue-system"
          f" --type='strategic' --patch='{patch_str}'"
      )
      return_code = run_command_with_updates_retry(
          patch_command, "Patch Kueue Tolerations", Namespace(dry_run=dry_run)
      )
      if return_code != 0:
        return return_code

    # Step 3: Wait for Kueue to be available
    return self._wait_for_kueue_available(dry_run)

  def _wait_for_kueue_available(self, dry_run: bool = False) -> int:
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
    return_code = run_command_with_updates(
        command, task, Namespace(dry_run=dry_run)
    )
    if return_code != 0:
      xpk_print(f"{task} returned ERROR {return_code}")
    return return_code

  def _configure(
      self,
      kueue_config: KueueConfig,
      dry_run: bool = False,
  ) -> int:
    """
    Configures Kueue with opinionated defaults for XPK.

    Args:
        kueue_config: The KueueConfig object containing all configuration parameters.
    Returns:
        0 if successful and 1 otherwise.
    """
    template = self.template_env.get_template(KUEUE_CONFIG_JINJA_FILE)

    # The manager builds the context internally based on its opinionated logic
    context = self._build_template_context(
        kueue_config.system,
        kueue_config.total_chips,
        kueue_config.is_pathways_cluster,
        kueue_config.autoprovisioning_enabled,
        kueue_config.flex,
        kueue_config.num_slices,
    )

    rendered_manifest = template.render(context)

    if kueue_config.system.device_type in [
        H100_MEGA_DEVICE_TYPE,
        H200_DEVICE_TYPE,
        B200_DEVICE_TYPE,
    ]:
      topology_yaml = self.template_env.get_template(KUEUE_TOPOLOGY_JINJA_FILE)
      rendered_manifest = topology_yaml.render() + rendered_manifest

    return_code = self._apply_manifest(rendered_manifest)
    if return_code != 0:
      return return_code

    return self._update_kueue_resources_if_necessary(dry_run)

  def _build_template_context(
      self,
      system,
      total_chips,
      is_pathways,
      autoprovisioning,
      flex,
      num_slices,
  ) -> Dict[str, Any]:
    """Prepares the context for the Jinja2 template."""
    # Main accelerator flavor
    device_type_str = system.device_type.replace("_", "-")
    main_flavor_name = f"{num_slices}x{device_type_str}"

    node_labels_dict = {}
    accelerator_label = create_accelerator_label(
        system.accelerator_type, system
    )
    key, value = accelerator_label.split(":", 1)
    node_labels_dict[key] = value.strip()
    machine_label = create_machine_label(
        system.accelerator_type, system, autoprovisioning
    )
    key, value = machine_label.split(":", 1)
    node_labels_dict[key] = value.strip()

    topology_label = ""
    if system.device_type in [
        H100_MEGA_DEVICE_TYPE,
        H200_DEVICE_TYPE,
        B200_DEVICE_TYPE,
    ]:
      topology_label = 'topologyName: "gke-default"'

    flavors = [{
        "name": main_flavor_name,
        "nodeLabels": node_labels_dict,
        "topologyLabel": topology_label,
    }]

    managed_resource = AcceleratorTypeToAcceleratorCharacteristics[
        system.accelerator_type
    ].resource_type

    # Main resource group
    resource_groups = [{
        "coveredResources": [managed_resource],
        "flavors": [{
            "name": main_flavor_name,
            "resources": [
                {"name": managed_resource, "nominalQuota": total_chips},
            ],
        }],
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

    if flex:
      admission_checks = """
        admissionChecks:
        - dws-prov
      """
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

  def _apply_manifest(self, manifest: str, dry_run: bool = False) -> int:
    task = "Applying Kueue Custom Resources"
    tmp_file = write_tmp_file(manifest)
    command = f"kubectl apply -f {tmp_file}"
    return run_command_with_updates(command, task, Namespace(dry_run=dry_run))

  def _update_kueue_resources_if_necessary(self, dry_run: bool = False) -> int:
    # Patch memory size limit if necessary
    # Get total number of nodes
    cmd_total_node_num = "kubectl get node --no-headers | wc -l"
    return_code, out = run_command_for_value(
        cmd_total_node_num, "Count total nodes", Namespace(dry_run=dry_run)
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
        Namespace(dry_run=dry_run),
    )
    if return_code != 0:
      xpk_print(f"{task} returned ERROR {return_code}")
    return return_code
