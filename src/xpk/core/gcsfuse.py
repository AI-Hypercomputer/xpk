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

from ..utils import templates

FUSE_PV_PATH = "/../templates/fuse-pv.yaml"
FUSE_PVC_PATH = "/../templates/fuse-pvc.yaml"


def create_pv(
    name: str,
    size: int,
    bucket: str,
    mount_options: str,
    prefetch_metadata: bool,
) -> dict:
  data = templates.load(FUSE_PV_PATH)
  data["metadata"]["name"] = f"{name}-pv"
  data["spec"]["capacity"]["storage"] = f"{size}Gi"
  data["spec"]["csi"]["volumeHandle"] = bucket
  if prefetch_metadata:
    data["spec"]["csi"]["volumeAttributes"][
        "gcsfuseMetadataPrefetchOnMount"
    ] = "true"
  data["spec"]["mountOptions"] = mount_options.split(",")
  return data


def create_pvc(name: str, size: int) -> dict:
  data = templates.load(FUSE_PVC_PATH)
  data["metadata"]["name"] = f"{name}-pvc"
  data["spec"]["resources"]["requests"]["storage"] = f"{size}Gi"
  data["spec"]["volumeName"] = f"{name}-pv"
  return data


def manifest(
    name: str,
    bucket: str,
    size: int,
    mount_options: str,
    prefetch_metadata: bool,
) -> list[dict]:
  """Creates GCS FUSE storage manifest file.

  Args:
      name (str): base name of the volumes
      bucket (str): name of the storage bucket
      size (str): size of the storage (in GB)
      prefetch_metadata (bool): if set, then enables metadata pre-population when mounting the volume
      mount_options (str): comma-separated list of mountOptions for PersistentVolume

  Returns:
      list[dict]: list of manifests
  """
  pv = create_pv(name, size, bucket, mount_options, prefetch_metadata)
  pvc = create_pvc(name, size)
  return [pv, pvc]
