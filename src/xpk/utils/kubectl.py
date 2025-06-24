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
import requests
import yaml
import packaging
from packaging.version import Version

from kubernetes.client.exceptions import ApiException
from kubernetes.dynamic import DynamicClient

from ..core.cluster import JOBSET_VERSION
from ..core.commands import run_command_for_value
from ..core.kueue import get_kueue_version, KUEUE_VERSION
from .console import xpk_print

MEMORY_SIZE_PER_VM = 1.2
MIN_MEMORY_LIMIT_SIZE = 4096

def apply_kubectl_manifest(client, manifest) -> int:
  xpk_print('Applying manifest')
  dynamic_client = DynamicClient(client)

  status_code = 0
  for obj in manifest:
    api_version = obj['apiVersion']
    kind = obj['kind']
    namespace = obj.get('metadata', {}).get('namespace', 'default')

    api_resource = dynamic_client.resources.get(
        api_version=api_version, kind=kind
    )

    try:
      api_resource.get(name=obj['metadata']['name'], namespace=namespace)
      api_resource.patch(
          body=obj,
          namespace=namespace,
          name=obj['metadata']['name'],
          content_type='application/merge-patch+json',
      )
      xpk_print(
          f"Updated {kind} '{obj['metadata']['name']}' in namespace"
          f" '{namespace}'"
      )

    except ApiException as e:
      if e.status == 404:
        api_resource.create(body=obj, namespace=namespace)
        xpk_print(
            f"Applied {kind} '{obj['metadata']['name']}' in namespace"
            f" '{namespace}'"
        )
      else:
        xpk_print(f'Error applying {kind}: {e}')
        status_code = 1
  return status_code

def get_jobset_manifest():
  """Get the jobset manifest.

  Returns:
    The updated jobset manifest.
  """
  manifest_url = f"https://github.com/kubernetes-sigs/jobset/releases/download/{JOBSET_VERSION}/manifests.yaml"
  manifest_content = None
  # Fetch the manifest content
  try:
    response = requests.get(manifest_url, timeout=10)
    response.raise_for_status()  # Raise an exception for HTTP errors
    manifest_content = response.text
    return manifest_content
  except requests.exceptions.Timeout as e:
    xpk_print(f"Error: Request to {manifest_url} after 10 seconds: {e}")
    xpk_exit(1)
  except requests.exceptions.RequestException as e:
    xpk_print(f"Error fetching manifest from {manifest_url}: {e}")
    xpk_exit(1)

  if manifest_content is None:
    xpk_print("Manifest content not found.")
    xpk_exit(1)


def update_jobset_resources_if_necessary(args):
  """Update the jobset manifest to increase the resources for the jobset controller manager.

  Args:
    args: user provided arguments for running the command.

  Returns:
    The updated jobset manifest.
  """
  manifest_content = get_jobset_manifest()
  # Load all YAML documents from the manifest
  yaml_data_list = list(yaml.safe_load_all(manifest_content))
  # Iterate through the yaml_data to find the Deployment for
  # jobset-controller-manager
  update_manifest = False
  for yaml_data in yaml_data_list:
    if (
        yaml_data
        and yaml_data.get("apiVersion") == "apps/v1"
        and yaml_data.get("kind") == "Deployment"
        and yaml_data.get("metadata", {}).get("name")
        == "jobset-controller-manager"
    ):
      # Found the Deployment, now modify the resources
      containers = yaml_data["spec"]["template"]["spec"]["containers"]
      for container in containers:
        if container["name"] == "manager":
          # Update memory limit
          current_memory_limit = (
              container["resources"].get("limits", {}).get("memory", "0Mi")
          )

          # Define new values for comparison
          cmd_total_node_num = (
              'kubectl get node --no-headers | wc -l'
          )
          return_code, out = run_command_for_value(
              cmd_total_node_num, 'Count total nodes', args
          )
          if return_code != 0:
            xpk_exit(1)
          # 1.2MiB per VM or 4GiB (whichever is greater).
          new_memory_limit = f"{max(math.ceil(int(out) * MEMORY_SIZE_PER_VM), MIN_MEMORY_LIMIT_SIZE)}Mi"
          if parse_resource_value(current_memory_limit) < parse_resource_value(
              new_memory_limit
          ):
            container["resources"]["limits"]["memory"] = new_memory_limit
            update_manifest = True
          break
      if update_manifest:
        xpk_print("Jobset controller updation required.")
        return update_manifest, yaml_data
  xpk_print("Jobset controller no updation required.")
  return update_manifest, yaml_data

def get_kueue_manifest():
  """Get the kueue manifest.

  Returns:
    The updated kueue manifest.
  """
  manifest_url = f"https://github.com/kubernetes-sigs/kueue/releases/download/{KUEUE_VERSION}/manifests.yaml"
  manifest_content = None
  # Fetch the manifest content
  try:
    response = requests.get(manifest_url, timeout=10)
    response.raise_for_status()  # Raise an exception for HTTP errors
    manifest_content = response.text
    return manifest_content
  except requests.exceptions.Timeout as e:
    xpk_print(f"Error: Request to {manifest_url} after 10 seconds: {e}")
    xpk_exit(1)
  except requests.exceptions.RequestException as e:
    xpk_print(f"Error fetching manifest from {manifest_url}: {e}")
    xpk_exit(1)

  if manifest_content is None:
    xpk_print("Manifest content not found.")
    xpk_exit(1)

def update_kueue_resources_if_necessary(args):
  """Update the kueue manifest to increase the resources for the kueue controller manager.

  Args:
    args: user provided arguments for running the command.

  Returns:
    The updated kueue manifest.
  """
  err_code, kueue_version_installed = get_kueue_version(args)
  if err_code == 0:
    if Version(kueue_version_installed) < Version('v0.9.0') and Version(
        KUEUE_VERSION
    ) >= Version('v0.9.0'):
      xpk_print('Upgrading kueue on cluster from version < 0.9.0.')
      upgrade_code = delete_multikueueclusters_definitions(args)
      if upgrade_code != 0:
        return upgrade_code
      upgrade_code = delete_multikueueconfigs_definitions(args)
      if upgrade_code != 0:
        return upgrade_code
  manifest_content = get_kueue_manifest()
  # Load all YAML documents from the manifest
  yaml_data_list = list(yaml.safe_load_all(manifest_content))
  # Iterate through the yaml_data to find the Deployment for
  # kueue-controller-manager
  update_manifest = False
  for yaml_data in yaml_data_list:
    if (
        yaml_data
        and yaml_data.get("apiVersion") == "apps/v1"
        and yaml_data.get("kind") == "Deployment"
        and yaml_data.get("metadata", {}).get("name")
        == "kueue-controller-manager"
    ):
      # Found the Deployment, now modify the resources
      containers = yaml_data["spec"]["template"]["spec"]["containers"]
      for container in containers:
        if container["name"] == "manager":
          # Update memory limit
          current_memory_limit = (
              container["resources"].get("limits", {}).get("memory", "0Mi")
          )

          # Define new values for comparison
          cmd_total_node_num = (
              'kubectl get node --no-headers | wc -l'
          )
          return_code, out = run_command_for_value(
              cmd_total_node_num, 'Count total nodes', args
          )
          if return_code != 0:
            xpk_exit(1)
          # 1.2MiB per VM or 4GiB (whichever is greater).
          new_memory_limit = f"{max(math.ceil(int(out) * MEMORY_SIZE_PER_VM), MIN_MEMORY_LIMIT_SIZE)}Mi"
          if parse_resource_value(current_memory_limit) < parse_resource_value(
              new_memory_limit
          ):
            container["resources"]["limits"]["memory"] = new_memory_limit
            update_manifest = True
          break
      if update_manifest:
        xpk_print("Kueue controller updation required.")
        return update_manifest, yaml_data
  xpk_print("Kueue controller no updation required.")
  return update_manifest, yaml_data

def parse_resource_value(value) -> int:
  if value.endswith("m"):
    return int(value[:-1])
  if value.endswith("Mi"):
    return int(value[:-2])
  if value.endswith("Gi"):
    return int(value[:-2]) * 1024
  return int(value)