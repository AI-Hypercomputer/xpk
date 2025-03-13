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


def decorate_kjob_template(job_manifest) -> str:
  spec = (
      job_manifest.setdefault('spec', {})
      .setdefault('template', {})
      .setdefault('spec', {})
  )
  spec.setdefault('tolerations', [])
  spec.setdefault('volumes', [])

  add_volumes(job_manifest)
  add_tolerations(job_manifest)
  update_gpu_containers(job_manifest)
  return job_manifest


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


def get_interfaces_entry(sub_networks: list[str]) -> tuple[str, str]:
  interfaces = [
      '[',
      '    {"interfaceName":"eth0","network":"default"},',
      *[
          f'    {{"interfaceName":"eth{i + 1}","network":"{sub_networks[i]}"}}{"," if i<8 else ""}'
          for i in range(9)
      ],
      ']',
  ]
  return 'networking.gke.io/interfaces', literal_string('\n'.join(interfaces))


def add_annotations(job_manifest, sub_networks):
  """Adds or updates annotations in the Pod template."""
  annotations = job_manifest['spec']['template']['metadata']['annotations']
  interfaces_key, interfaces_value = get_interfaces_entry(sub_networks)
  annotations.update({
      'networking.gke.io/default-interface': "'eth0'",
      interfaces_key: interfaces_value,
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
