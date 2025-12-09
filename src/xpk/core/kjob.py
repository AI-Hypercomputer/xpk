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

from kubernetes import client as k8s_client
from kubernetes.client import ApiClient
from kubernetes.client.rest import ApiException

from ..utils import templates
from ..utils.console import xpk_exit, xpk_print
from .cluster import DEFAULT_NAMESPACE

KJOB_API_GROUP_NAME = "kjobctl.x-k8s.io"
KJOB_API_GROUP_VERSION = "v1alpha1"
KJOB_API_VOLUME_BUNDLE_PLURAL = "volumebundles"
VOLUME_BUNDLE_TEMPLATE_PATH = "/../templates/volume_bundle.yaml"


def create_volume_bundle_instance(
    k8s_api_client: ApiClient,
    name: str,
    manifest: list[dict],
    readonly: bool,
    mount_point: str,
) -> None:
  """
  Creates a new VolumeBundle resource in the Kubernetes cluster.

  This function reads a VolumeBundle template from a YAML file, populates it with
  values from the provided arguments, and then creates the VolumeBundle object
  in the cluster.

  Args:
      k8s_api_client: An ApiClient object for interacting with the Kubernetes API.
      args: An argparse Namespace object containing the arguments for creating
            the Storage resource.
  """
  data = templates.load(VOLUME_BUNDLE_TEMPLATE_PATH)
  data["metadata"]["name"] = name
  spec = data["spec"]
  spec["volumes"] = []
  spec["containerVolumeMounts"] = []

  for obj in manifest:
    if obj["kind"] == "PersistentVolumeClaim":
      spec["volumes"].append({
          "name": obj["metadata"]["name"],
          "persistentVolumeClaim": {
              "claimName": obj["metadata"]["name"],
              "readOnly": readonly,
          },
      })
      spec["containerVolumeMounts"].append({
          "name": obj["metadata"]["name"],
          "mountPath": mount_point,
      })

  data["spec"] = spec

  api_instance = k8s_client.CustomObjectsApi(k8s_api_client)
  try:
    api_instance.create_namespaced_custom_object(
        namespace=DEFAULT_NAMESPACE,
        group=KJOB_API_GROUP_NAME,
        version=KJOB_API_GROUP_VERSION,
        plural=KJOB_API_VOLUME_BUNDLE_PLURAL,
        body=data,
    )
    xpk_print(
        f"Created {KJOB_API_VOLUME_BUNDLE_PLURAL}.{KJOB_API_GROUP_NAME} object:"
        f" {data['metadata']['name']}"
    )
  except ApiException as e:
    if e.status == 409:
      xpk_print(f"VolumeBundle: {name} already exists. Skipping its creation")
    else:
      xpk_print(f"Encountered error during VolumeBundle creation: {e}")
      xpk_exit(1)
