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
import functools
from typing import Callable
from ...core.storage import GCS_FUSE_TYPE, get_storage_volumes_yaml_dict, Storage


def apply(
    func: Callable[[str, list[str]], str],
) -> Callable[[str, list[str], list[Storage]], str]:
  """
  Decorates a JobSet modyfying function with additional logic to apply storage data.

  Args:
    func: the JobSet modyfiyng function

  Returns:
    The modified operator that includes storage.
  """

  @functools.wraps(func)
  def wrapper(yml_string, sub_networks, storages) -> str:

    jobset_manifest_str = func(yml_string, sub_networks)
    if len(storages) == 0:
      return jobset_manifest_str

    manifest = yaml.safe_load(jobset_manifest_str)
    storage_volumes = get_storage_volumes_yaml_dict(storages)
    for job in manifest['spec']['replicatedJobs']:
      job_manifest = job['template']
      add_annotations(job_manifest, storages)
      add_volumes(job_manifest, storage_volumes)
    return yaml.dump(manifest, sort_keys=False)

  return wrapper


def add_annotations(job_manifest, storages):
  """Adds or updates storage annotations in the Pod template."""
  annotations = job_manifest['spec']['template']['metadata']['annotations']
  gcs_present = [storage.type == GCS_FUSE_TYPE for storage in storages]
  if gcs_present:
    annotations.update({'gke-gcsfuse/volumes': 'true'})


def add_volumes(job_manifest, storage_volumes):
  volumes = job_manifest['spec']['template']['spec']['volumes']
  volumes.extend(storage_volumes)
