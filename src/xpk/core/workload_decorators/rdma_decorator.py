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
from ...utils.yaml import literal_string
from ...core.storage import GCS_FUSE_TYPE, get_storage_volumes_yaml_dict


def decorate_jobset(jobset_manifest_str, sub_networks) -> str:
  """
  Decorates a JobSet manifest with the necessary components for rdma-daemon.

  Args:
    jobset_manifest_str: The JobSet manifest as a YAML string.

  Returns:
    The modified JobSet manifest as a YAML string.
  """

  manifest = yaml.safe_load(jobset_manifest_str)

  for job in manifest['spec']['replicatedJobs']:
    job_manifest = job['template']
    job_manifest.setdefault('spec', {}).setdefault('template', {}).setdefault(
        'metadata', {}
    ).setdefault('annotations', {})
    spec = (
        job_manifest.setdefault('spec', {})
        .setdefault('template', {})
        .setdefault('spec', {})
    )
    spec.setdefault('tolerations', [])
    spec.setdefault('volumes', [])

    add_annotations(job_manifest, sub_networks)
    add_volumes(job_manifest)
    add_tolerations(job_manifest)
    update_gpu_containers(job_manifest)

  return yaml.dump(manifest, sort_keys=False)


def decorate_jobset_with_storages(jobset_manifest_str, storages) -> str:
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
    add_storage_annotations(job_manifest, storages)
    add_storage_volumes(job_manifest, storage_volumes)

  return yaml.dump(manifest, sort_keys=False)


def add_storage_annotations(job_manifest, storages):
  """Adds or updates storage annotations in the Pod template."""
  annotations = job_manifest['spec']['template']['metadata']['annotations']
  gcs_present = [storage.type == GCS_FUSE_TYPE for storage in storages]
  if gcs_present:
    annotations.update({'gke-gcsfuse/volumes': 'true'})


def add_storage_volumes(job_manifest, volumes):
  volumes = job_manifest['spec']['template']['spec']['volumes']
  volumes.extend(volumes)


def add_annotations(job_manifest, sub_networks):
  """Adds or updates annotations in the Pod template."""
  annotations = job_manifest['spec']['template']['metadata']['annotations']
  interfaces = [
      '[',
      '    {"interfaceName":"eth0","network":"default"},',
      *[
          f'    {{"interfaceName":"eth{i + 1}","network":"{sub_networks[i]}"}}{"," if i<8 else ""}'
          for i in range(9)
      ],
      ']',
  ]
  annotations.update({
      'networking.gke.io/default-interface': 'eth0',
      'networking.gke.io/interfaces': literal_string('\n'.join(interfaces)),
  })


def add_volumes(job_manifest):
  """Adds volumes to the Pod spec."""
  volumes = job_manifest['spec']['template']['spec']['volumes']
  volumes.append({
      'name': 'library-dir-host',
      'hostPath': {'path': '/home/kubernetes/bin/nvidia'},
  })
  volumes.append(
      {'name': 'gib', 'hostPath': {'path': '/home/kubernetes/bin/gib'}}
  )


def add_tolerations(job_manifest):
  """Adds tolerations to the Pod spec."""
  tolerations = job_manifest['spec']['template']['spec']['tolerations']
  tolerations.append({
      'key': 'user-workload',
      'operator': 'Equal',
      'value': 'true',
      'effect': 'NoSchedule',
  })


def update_gpu_containers(job_manifest):
  for container in job_manifest['spec']['template']['spec']['containers']:
    if 'nvidia.com/gpu' in container.get('resources', {}).get('limits', {}):
      container.setdefault('env', [])
      container['env'].append(
          {'name': 'LD_LIBRARY_PATH', 'value': '/usr/local/nvidia/lib64'}
      )
      container.setdefault('volumeMounts', [])
      container['volumeMounts'].append(
          {'name': 'library-dir-host', 'mountPath': '/usr/local/nvidia'}
      )
      container['volumeMounts'].append(
          {'name': 'gib', 'mountPath': '/usr/local/gib'}
      )
