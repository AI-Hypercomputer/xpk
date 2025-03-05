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

import os

import ruamel.yaml

yaml = ruamel.yaml.YAML()
yaml_object_separator = "---\n"

FUSE_PV_PATH = "/../templates/fuse-pv.yaml"
FUSE_PVC_PATH = "/../templates/fuse-pvc.yaml"


def create_pv(name: str, size: int, bucket: str) -> dict:
  template_path = os.path.dirname(__file__) + FUSE_PV_PATH
  with open(template_path, "r", encoding="utf-8") as file:
    data: dict = yaml.load(file)
  data["metadata"]["name"] = f"{name}-pv"
  data["spec"]["capacity"]["storage"] = f"{size}Gi"
  data["spec"]["csi"]["volumeHandle"] = bucket
  return data


def create_pvc(name: str, size: int) -> dict:
  template_path = os.path.dirname(__file__) + FUSE_PVC_PATH
  with open(template_path, "r", encoding="utf-8") as file:
    data: dict = yaml.load(file)
  data["metadata"]["name"] = f"{name}-pvc"
  data["spec"]["resources"]["requests"]["storage"] = f"{size}Gi"
  data["spec"]["volumeName"] = f"{name}-pv"
  return data


def manifest(path: str, name: str, bucket: str, size: int) -> None:
  """Creates GCS FUSE manifest file.

  Args:
      path (str): path to the file where the manifest will be created
      name (str): base name of the volumes
      bucket (str): name of the storage bucket
      size (str): size of the storage
  """
  pv = create_pv(name, size, bucket)
  pvc = create_pvc(name, size)
  with open(path, "w", encoding="utf-8") as f:
    yaml.dump(pv, f)
    f.write(yaml_object_separator)
    yaml.dump(pvc, f)
