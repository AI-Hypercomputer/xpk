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

import ruamel.yaml

yaml = ruamel.yaml.YAML()


GCSFUSE_PV_TEMPLATE = """apiVersion: v1
kind: PersistentVolume
metadata:
  name: {name}-pv
spec:
  accessModes:
  - ReadWriteMany
  capacity:
    storage: {size}
  storageClassName: example-storage-class
  mountOptions:
    - implicit-dirs
  csi:
    driver: gcsfuse.csi.storage.gke.io
    volumeHandle: {bucket}
    volumeAttributes:
      gcsfuseLoggingSeverity: warning
"""

GCSFUSE_PVC_TEMPLATE = """apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: {name}-static-pvc
  namespace: default
spec:
  accessModes:
  - ReadWriteMany
  resources:
    requests:
      storage: {size}
  volumeName: {name}-pv
  storageClassName: example-storage-class
"""


def manifest(path: str, name: str, bucket: str, size: int):
  """Creates GCS FUSE manifest file.

  Args:
      path (str): path to the file where the manifest will be created
      name (str): base name of the volumes
      bucket (str): name of the storage bucket
      size (str): size of the storage
  """
  size = str(size) + "Gi"
  pv = GCSFUSE_PV_TEMPLATE.format(name=name, size=size, bucket=bucket)
  pvc = GCSFUSE_PVC_TEMPLATE.format(name=name, size=size)
  with open(path, "w", encoding="utf-8") as f:
    f.write(pv)
    f.write("---\n")
    f.write(pvc)
