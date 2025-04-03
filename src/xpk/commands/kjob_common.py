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

from ..core.capacity import (
    B200_DEVICE_TYPE,
    H100_MEGA_DEVICE_TYPE,
    H200_DEVICE_TYPE,
)
from ..core.cluster import get_gpu_type_from_cluster
from ..core.kjob import (
    get_a3mega_pod_template_annotations,
    get_a3ultra_pod_template_annotations,
    get_a4_pod_template_annotations,
)


def add_gpu_networking_annotations_to_command(args, cmd: str) -> str:
  gpu_type = get_gpu_type_from_cluster(args)

  if gpu_type == H100_MEGA_DEVICE_TYPE:
    annotations = get_a3mega_pod_template_annotations(args)
  elif gpu_type == H200_DEVICE_TYPE:
    annotations = get_a3ultra_pod_template_annotations(args)
  elif gpu_type == B200_DEVICE_TYPE:
    annotations = get_a4_pod_template_annotations()
  else:
    annotations = []

  flags = [
      f" --pod-template-annotation {annotation} " for annotation in annotations
  ]
  cmd += "\\\n".join(flags)

  return cmd
