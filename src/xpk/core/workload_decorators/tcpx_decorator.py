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

# Component version
tcpx = 'v2.0.11'


def decorate_job(job_manifest: dict) -> dict:
  add_annotations(job_manifest)
  add_volumes(job_manifest)
  add_tolerations(job_manifest)
  add_tcpx_daemon_container(job_manifest)
  update_gpu_containers(job_manifest)
  return job_manifest


def decorate_jobset(  # pylint: disable=dangerous-default-value
    jobset_manifest_str: str,
    sub_networks: list[str] = [],  # pylint: disable=unused-argument
) -> str:
  """
  Decorates a JobSet manifest with the necessary components for tcpxo-daemon.

  Args:
    jobset_manifest_str: The JobSet manifest as a YAML string.
    sub_networks: This parameter is accepted for interface consistency but is not used.

  Returns:
    The modified JobSet manifest as a YAML string.
  """

  manifest = yaml.safe_load(jobset_manifest_str)

  for job in manifest['spec']['replicatedJobs']:
    job_manifest = job['template']
    job_manifest = decorate_job(job_manifest)
  yaml_str: str = yaml.dump(manifest, sort_keys=False)
  return yaml_str


def get_interfaces_annotation() -> dict:
  interfaces = [
      '[',
      '    {"interfaceName":"eth0","network":"default"},',
      '    {"interfaceName":"eth1","network":"vpc1"},',
      '    {"interfaceName":"eth2","network":"vpc2"},',
      '    {"interfaceName":"eth3","network":"vpc3"},',
      '    {"interfaceName":"eth4","network":"vpc4"}',
      ']',
  ]
  return {'networking.gke.io/interfaces': literal_string('\n'.join(interfaces))}


def get_tcpx_deamon_annotation() -> dict:
  return {
      'devices.gke.io/container.tcpx-daemon': literal_string(
          '- path: /dev/nvidia0\n'
          '- path: /dev/nvidia1\n'
          '- path: /dev/nvidia2\n'
          '- path: /dev/nvidia3\n'
          '- path: /dev/nvidia4\n'
          '- path: /dev/nvidia5\n'
          '- path: /dev/nvidia6\n'
          '- path: /dev/nvidia7\n'
          '- path: /dev/nvidiactl\n'
          '- path: /dev/nvidia-uvm\n'
      )
  }


def add_annotations(job_manifest: dict):
  """Adds or updates annotations in the Pod template."""
  annotations: dict = (
      job_manifest.setdefault('spec', {})
      .setdefault('template', {})
      .setdefault('metadata', {})
      .setdefault('annotations', {})
  )
  annotations.update(get_tcpx_deamon_annotation())
  annotations.update({'networking.gke.io/default-interface': 'eth0'})
  annotations.update(get_interfaces_annotation())


def add_tolerations(job_manifest: dict):
  """Adds tolerations to the Pod spec."""
  tolerations: list = (
      job_manifest.setdefault('spec', {})
      .setdefault('template', {})
      .setdefault('spec', {})
      .setdefault('tolerations', [])
  )
  tolerations.append({
      'key': 'user-workload',
      'operator': 'Equal',
      'value': 'true',
      'effect': 'NoSchedule',
  })


def add_volumes(job_manifest: dict):
  """Adds volumes to the Pod spec."""
  volumes: list = (
      job_manifest.setdefault('spec', {})
      .setdefault('template', {})
      .setdefault('spec', {})
      .setdefault('volumes', [])
  )
  volumes.append({
      'name': 'libraries',
      'hostPath': {'path': '/home/kubernetes/bin/nvidia/lib64'},
  })
  volumes.append({'name': 'sys', 'hostPath': {'path': '/sys'}})
  volumes.append({'name': 'proc-sys', 'hostPath': {'path': '/proc/sys'}})
  volumes.append({'name': 'tcpx-socket', 'hostPath': {'path': '/run/tcpx'}})
  volumes.append(
      {'name': 'dshm', 'emptyDir': {'medium': 'Memory', 'sizeLimit': '128Gi'}}
  )


def add_tcpx_daemon_container(job_manifest):
  """Adds the tcpx-daemon container to the Pod spec."""
  tcpxo_daemon_container = {
      'name': 'tcpx-daemon',
      'image': f'us-docker.pkg.dev/gce-ai-infra/gpudirect-tcpx/tcpgpudmarxd-dev:{tcpx}',
      'imagePullPolicy': 'Always',
      'restartPolicy': 'Always',
      'command': [
          '/tcpgpudmarxd/build/app/tcpgpudmarxd',
          '--gpu_nic_preset',
          'a3vm',
          '--gpu_shmem_type',
          'fd',
          '--uds_path',
          '/run/tcpx',
          '--setup_param',
          '"--verbose 128 2 0 "',
      ],
      'securityContext': {'capabilities': {'add': ['NET_ADMIN']}},
      'volumeMounts': [
          {'name': 'libraries', 'mountPath': '/usr/local/nvidia/lib64'},
          {'name': 'tcpx-socket', 'mountPath': '/run/tcpx'},
          {'name': 'sys', 'mountPath': '/hostsysfs'},
          {'name': 'proc-sys', 'mountPath': '/hostprocsysfs'},
      ],
      'env': [{'name': 'LD_LIBRARY_PATH', 'value': '/usr/local/nvidia/lib64'}],
  }
  spec = job_manifest['spec']['template']['spec']
  spec.setdefault('initContainers', [])
  spec['initContainers'].append(tcpxo_daemon_container)


def update_gpu_containers(job_manifest) -> None:
  for container in job_manifest['spec']['template']['spec']['containers']:
    if 'nvidia.com/gpu' in container.get('resources', {}).get('limits', {}):
      env: list = container.setdefault('env', [])
      env.append(
          {'name': 'LD_LIBRARY_PATH', 'value': '/usr/local/nvidia/lib64'}
      )
      volumeMounts: list = container.setdefault('volumeMounts', [])
      volumeMounts.append({'name': 'tcpx-socket', 'mountPath': '/tmp'})
      volumeMounts.append(
          {'name': 'libraries', 'mountPath': '/usr/local/nvidia/lib64'}
      )
      container['volumeMounts'].append(
          {'name': 'dshm', 'mountPath': '/dev/shm'}
      )
