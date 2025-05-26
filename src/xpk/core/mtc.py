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

import requests
import yaml

from ..core.cluster import JOBSET_VERSION
from ..core.cluster import setup_k8s_env
from ..utils import templates
from ..utils.console import xpk_exit
from ..utils.console import xpk_print
from ..utils.kubectl import apply_kubectl_manifest


MTC_CPC_PATH = "/../templates/mtc-cpc.yaml"


def create_mtc_cpc(
    mtc_gcs_bucket: str,
    mtc_machine_type: str,
    mtc_toleration_key: str,
    mtc_ramdisk_size: str,
) -> dict:
  """Create MTC Checkpoint Configuration.

  Args:
    mtc_gcs_bucket: GCS bucket for MTC
    mtc_machine_type: Machine type for MTC
    mtc_toleration_key: Toleration key for MTC
    mtc_ramdisk_size: Ramdisk size for MTC

  Returns:
    MTC Checkpoint Configuration
  """
  data = templates.load(MTC_CPC_PATH)

  data["spec"]["cloudStorageBucketName"] = mtc_gcs_bucket
  data["spec"]["nodeSelector"][
      "node.kubernetes.io/instance-type"
  ] = mtc_machine_type
  data["spec"]["tolerations"][0]["key"] = mtc_toleration_key
  data["spec"]["inMemoryVolumeSize"] = mtc_ramdisk_size

  return data


def install_mtc_on_cluster(args, system) -> int:
  """Install MTC on the cluster.

  Args:
    args: user provided arguments for running the command.
    system: system related information.

  Returns:
    return code of the command.
  """
  if args.mtc_gcs_bucket is None:
    xpk_print("MTC GCS bucket is required.")
    xpk_exit(1)
  if args.mtc_gcs_bucket.startswith("gs://"):
    args.mtc_gcs_bucket = args.mtc_gcs_bucket.replace("gs://", "")

  if args.mtc_ramdisk_size is None:
    xpk_print("MTC ramdisk size is required.")
    xpk_exit(1)

  if args.mtc_toleration_key is None:
    args.mtc_toleration_key = "google.com/tpu"

  k8s_api_client = setup_k8s_env(args)
  jobset_manifest = update_jobset_manifest()
  if jobset_manifest is None:
    xpk_print(
        "Updated jobset manifest is empty, not updating the jobset controller."
    )

  xpk_print("Applying Jobset with MTC Configuration")
  return_code = apply_kubectl_manifest(k8s_api_client, [jobset_manifest])
  if return_code != 0:
    return return_code

  mtc_checkpoint_configuration_crd_data = create_mtc_cpc(
      args.mtc_gcs_bucket,
      system.gce_machine_type,
      args.mtc_toleration_key,
      args.mtc_ramdisk_size,
  )
  xpk_print("Applying MTC Checkpoint Configuration")
  return_code = apply_kubectl_manifest(
      k8s_api_client, [mtc_checkpoint_configuration_crd_data]
  )

  return return_code


def update_jobset_manifest():
  """Update the jobset manifest to increase the resources for the jobset controller manager.

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
  except requests.exceptions.Timeout as e:
    xpk_print(f"Error: Request to {manifest_url} after 10 seconds: {e}")
    xpk_exit(1)
  except requests.exceptions.RequestException as e:
    xpk_print(f"Error fetching manifest from {manifest_url}: {e}")
    xpk_exit(1)

  if manifest_content is None:
    xpk_print("Manifest content not found.")
    xpk_exit(1)

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
          # Update resource limits and requests
          current_cpu_request = (
              container["resources"].get("requests", {}).get("cpu", "0m")
          )
          current_memory_request = (
              container["resources"].get("requests", {}).get("memory", "0Mi")
          )
          current_memory_limit = (
              container["resources"].get("limits", {}).get("memory", "0Mi")
          )

          # Define new values for comparison
          new_cpu_request = "1000m"
          new_memory_request = "1Gi"
          new_memory_limit = "2Gi"

          if parse_resource_value(current_cpu_request) < parse_resource_value(
              new_cpu_request
          ):
            container["resources"]["requests"]["cpu"] = new_cpu_request
            update_manifest = True
          if parse_resource_value(
              current_memory_request
          ) < parse_resource_value(new_memory_request):
            container["resources"]["requests"]["memory"] = new_memory_request
            update_manifest = True
          if parse_resource_value(current_memory_limit) < parse_resource_value(
              new_memory_limit
          ):
            container["resources"]["limits"]["memory"] = new_memory_limit
            update_manifest = True
          break
      if update_manifest:
        xpk_print("Jobset controller updation required.")
        return yaml_data
  xpk_print("Jobset controller no updation required.")


def parse_resource_value(value) -> int:
  if value.endswith("m"):
    return int(value[:-1])
  if value.endswith("Mi"):
    return int(value[:-2])
  if value.endswith("Gi"):
    return int(value[:-2]) * 1024
  return int(value)
