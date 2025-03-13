"""
Copyright 2025 Google LLC

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

from ..core.resources import get_cluster_system_characteristics
from ..core.kjob import get_a3mega_pod_template_annotations, get_a3ultra_pod_template_annotations
from ..core.capacity import H100_MEGA_DEVICE_TYPE, H200_DEVICE_TYPE


def add_h100_mega_annotations(args, cmd: str) -> str:
  tcpxo, interfaces, eth0 = get_a3mega_pod_template_annotations(args)
  cmd += f" --pod-template-annotation {tcpxo} \\\n"
  cmd += f" --pod-template-annotation {eth0} \\\n"
  cmd += f" --pod-template-annotation {interfaces} "
  return cmd


def add_h200_ultra_annotations(args, cmd) -> str:
  eth0, interfaces = get_a3ultra_pod_template_annotations(args)
  cmd += f" --pod-template-annotation {eth0} \\\n"
  cmd += f" --pod-template-annotation {interfaces} \\\n"
  return cmd


def get_gpu_type_from_cluster(args) -> str:
  system = get_cluster_system_characteristics(args)
  if not system is None:
    return system.device_type
  return ""


def add_annotation_to_job(args, cmd: str) -> str:
  gpu_type = get_gpu_type_from_cluster(args)

  if gpu_type == H100_MEGA_DEVICE_TYPE:
    return add_h100_mega_annotations(args, cmd)
  if gpu_type == H200_DEVICE_TYPE:
    return add_h200_ultra_annotations(args, cmd)
  return cmd
