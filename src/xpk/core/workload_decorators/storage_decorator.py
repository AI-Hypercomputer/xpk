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

import yaml

from ...core.storage import GCS_FUSE_TYPE, get_storage_volumes_yaml_dict, GCS_FUSE_ANNOTATION


def decorate_jobset(jobset_manifest_str, storages) -> str:
  """
  Decorates a JobSet manifest with the necessary storages.

  Args:
    jobset_manifest_str: The JobSet manifest as a YAML string.

  Returns:
    The modified JobSet manifest as a YAML string.
  """

  manifest = yaml.safe_load(jobset_manifest_str)
  storage_volumes = get_storage_volumes_yaml_dict(storages)
  for job in manifest['spec']['replicatedJobs']:
    job_manifest = job['template']
    add_annotations(job_manifest, storages)
    add_volumes(job_manifest, storage_volumes)
  return yaml.dump(manifest, sort_keys=False)


def add_annotations(job_manifest, storages):
  """Adds or updates storage annotations in the Pod template."""
  annotations = job_manifest['spec']['template']['metadata']['annotations']
  gcs_present = [storage.type == GCS_FUSE_TYPE for storage in storages]
  if gcs_present:
    annotations.update(GCS_FUSE_ANNOTATION)


def add_volumes(job_manifest, storage_volumes):
  volumes = job_manifest['spec']['template']['spec']['volumes']
  volumes.extend(storage_volumes)
