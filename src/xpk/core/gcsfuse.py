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


def create_pv(name: str, size: int, bucket: str) -> dict:
  data = templates.load(FUSE_PV_PATH)
  data["metadata"]["name"] = f"{name}-pv"
  data["spec"]["capacity"]["storage"] = f"{size}Gi"
  data["spec"]["csi"]["volumeHandle"] = bucket
  return data


def create_pvc(name: str, size: int) -> dict:
  data = templates.load(FUSE_PVC_PATH)
  data["metadata"]["name"] = f"{name}-pvc"
  data["spec"]["resources"]["requests"]["storage"] = f"{size}Gi"
  data["spec"]["volumeName"] = f"{name}-pv"
  return data


def manifest(name: str, bucket: str, size: int) -> list[dict]:
  """Creates GCS FUSE manifest file.

  Args:
      path (str): path to the file where the manifest will be created
      name (str): base name of the volumes
      bucket (str): name of the storage bucket
      size (str): size of the storage
  """
  pv = create_pv(name, size, bucket)
  pvc = create_pvc(name, size)
  return [pv, pvc]
