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
rxdm = 'v1.0.12'


def decorate_kjob_template(job_manifest: dict) -> dict:
  spec = (
      job_manifest.setdefault('spec', {})
      .setdefault('template', {})
      .setdefault('spec', {})
  )
  spec.setdefault('tolerations', [])
  spec.setdefault('volumes', [])

  add_volumes(job_manifest)
  add_tolerations(job_manifest)
  add_tcpxo_daemon_container(job_manifest)
  update_gpu_containers(job_manifest)
  return job_manifest


def decorate_job(job_manifest: dict, sub_networks: list[str]) -> dict:
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
  add_tcpxo_daemon_container(job_manifest)
  update_gpu_containers(job_manifest)
  return job_manifest


def decorate_jobset(jobset_manifest_str, sub_networks) -> str:
  """
  Decorates a JobSet manifest with the necessary components for tcpxo-daemon.

  Args:
    jobset_manifest_str: The JobSet manifest as a YAML string.

  Returns:
    The modified JobSet manifest as a YAML string.
  """

  manifest = yaml.safe_load(jobset_manifest_str)

  for job in manifest['spec']['replicatedJobs']:
    job_manifest = job['template']
    job_manifest = decorate_job(job_manifest, sub_networks)
  return yaml.dump(manifest, sort_keys=False)


def get_interfaces_entry(sub_networks: list[str]) -> tuple[str, str]:
  interfaces = [
      '[',
      '    {"interfaceName":"eth0","network":"default"},',
      *[
          f'    {{"interfaceName":"eth{i + 1}","network":"{sub_networks[i]}"}}{"," if i<7 else ""}'
          for i in range(8)
      ],
      ']',
  ]
  return 'networking.gke.io/interfaces', literal_string('\n'.join(interfaces))


def get_tcpxo_deamon_entry() -> tuple[str, str]:
  return 'devices.gke.io/container.tcpxo-daemon', literal_string(
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
      '- path: /dev/dmabuf_import_helper\n'
  )


def add_annotations(job_manifest, sub_networks):
  """Adds or updates annotations in the Pod template."""
  annotations = job_manifest['spec']['template']['metadata']['annotations']
  tcpxo_deamon_key, tcpxo_deamon_paths = get_tcpxo_deamon_entry()
  interfaces_key, interfaces_value = get_interfaces_entry(sub_networks)
  annotations.update({
      tcpxo_deamon_key: tcpxo_deamon_paths,
      'networking.gke.io/default-interface': 'eth0',
      interfaces_key: interfaces_value,
  })


def add_tolerations(job_manifest):
  """Adds tolerations to the Pod spec."""
  tolerations = job_manifest['spec']['template']['spec']['tolerations']
  tolerations.append({
      'key': 'user-workload',
      'operator': 'Equal',
      'value': 'true',
      'effect': 'NoSchedule',
  })


def add_volumes(job_manifest):
  """Adds volumes to the Pod spec."""
  volumes = job_manifest['spec']['template']['spec']['volumes']
  volumes.append({
      'name': 'libraries',
      'hostPath': {'path': '/home/kubernetes/bin/nvidia'},
  })
  volumes.append({'name': 'sys', 'hostPath': {'path': '/sys'}})
  volumes.append({'name': 'proc-sys', 'hostPath': {'path': '/proc/sys'}})
  volumes.append({
      'name': 'aperture-devices',
      'hostPath': {'path': '/dev/aperture_devices'},
  })


def add_tcpxo_daemon_container(job_manifest):
  """Adds the tcpxo-daemon container to the Pod spec."""
  tcpxo_daemon_container = {
      'name': 'tcpxo-daemon',
      'image': f'us-docker.pkg.dev/gce-ai-infra/gpudirect-tcpxo/tcpgpudmarxd-dev:{rxdm}',
      'imagePullPolicy': 'Always',
      'command': ['/bin/sh', '-c'],
      'args': [
          'set -ex\nchmod 755'
          ' /fts/entrypoint_rxdm_container.sh\n/fts/entrypoint_rxdm_container.sh'
          ' --num_hops=2 --num_nics=8 --uid= --alsologtostderr'
      ],
      'securityContext': {
          'capabilities': {'add': ['NET_ADMIN', 'NET_BIND_SERVICE']}
      },
      'volumeMounts': [
          {'name': 'libraries', 'mountPath': '/usr/local/nvidia'},
          {'name': 'sys', 'mountPath': '/hostsysfs'},
          {'name': 'proc-sys', 'mountPath': '/hostprocsysfs'},
      ],
      'env': [{'name': 'LD_LIBRARY_PATH', 'value': '/usr/local/nvidia/lib64'}],
  }
  job_manifest['spec']['template']['spec']['containers'].append(
      tcpxo_daemon_container
  )


def update_gpu_containers(job_manifest):
  for container in job_manifest['spec']['template']['spec']['containers']:
    if 'nvidia.com/gpu' in container.get('resources', {}).get('limits', {}):
      container.setdefault('env', [])
      container['env'].append(
          {'name': 'LD_LIBRARY_PATH', 'value': '/usr/local/nvidia/lib64'}
      )
      container['env'].append({
          'name': 'NCCL_FASTRAK_LLCM_DEVICE_DIRECTORY',
          'value': '/dev/aperture_devices',
      })
      container.setdefault('volumeMounts', [])
      container['volumeMounts'].append(
          {'name': 'aperture-devices', 'mountPath': '/dev/aperture_devices'}
      )
      container['volumeMounts'].append(
          {'name': 'libraries', 'mountPath': '/usr/local/nvidia'}
      )
