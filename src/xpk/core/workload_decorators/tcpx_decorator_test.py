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

import copy

import yaml

from xpk.core.workload_decorators import tcpx_decorator
from xpk.utils.yaml import literal_string

# Minimal JobSet manifest for testing
BASE_JOBSET_MANIFEST_STR = """
apiVersion: jobset.x-k8s.io/v1alpha2
kind: JobSet
metadata:
  name: test-jobset
spec:
  replicatedJobs:
    - name: slice-job
      template:
        spec:
          template:
            metadata:
              annotations:
                existing-annotation: "true"
            spec:
              containers:
              - name: main-gpu-container
                image: my-gpu-image
                resources:
                  limits:
                    nvidia.com/gpu: 8
              - name: sidecar-container
                image: my-sidecar-image
"""

# Minimal job manifest for testing
BASE_JOB_MANIFEST = {
    "spec": {
        "template": {
            "metadata": {"annotations": {"existing-annotation": "true"}},
            "spec": {
                "containers": [
                    {
                        "name": "main-gpu-container",
                        "image": "my-gpu-image",
                        "resources": {"limits": {"nvidia.com/gpu": 8}},
                    },
                    {"name": "sidecar-container", "image": "my-sidecar-image"},
                ]
            },
        }
    }
}


def test_get_interfaces_annotation():
  """Tests get_interfaces_annotation."""
  annotation = tcpx_decorator.get_interfaces_annotation()
  assert "networking.gke.io/interfaces" in annotation
  assert isinstance(annotation["networking.gke.io/interfaces"], literal_string)
  expected_value = (
      "[\n"
      '    {"interfaceName":"eth0","network":"default"},\n'
      '    {"interfaceName":"eth1","network":"vpc1"},\n'
      '    {"interfaceName":"eth2","network":"vpc2"},\n'
      '    {"interfaceName":"eth3","network":"vpc3"},\n'
      '    {"interfaceName":"eth4","network":"vpc4"}\n'
      "]"
  )
  assert str(annotation["networking.gke.io/interfaces"]) == expected_value


def test_get_tcpx_deamon_annotation():
  """Tests get_tcpx_deamon_annotation."""
  annotation = tcpx_decorator.get_tcpx_deamon_annotation()
  assert "devices.gke.io/container.tcpx-daemon" in annotation
  assert isinstance(
      annotation["devices.gke.io/container.tcpx-daemon"], literal_string
  )
  expected_value = (
      "- path: /dev/nvidia0\n"
      "- path: /dev/nvidia1\n"
      "- path: /dev/nvidia2\n"
      "- path: /dev/nvidia3\n"
      "- path: /dev/nvidia4\n"
      "- path: /dev/nvidia5\n"
      "- path: /dev/nvidia6\n"
      "- path: /dev/nvidia7\n"
      "- path: /dev/nvidiactl\n"
      "- path: /dev/nvidia-uvm\n"
  )
  assert (
      str(annotation["devices.gke.io/container.tcpx-daemon"]) == expected_value
  )


def test_decorate_jobset():
  """Tests decorate_jobset."""
  decorated_str = tcpx_decorator.decorate_jobset(BASE_JOBSET_MANIFEST_STR)
  manifest = yaml.safe_load(decorated_str)

  pod_template_spec = manifest["spec"]["replicatedJobs"][0]["template"]["spec"][
      "template"
  ]["spec"]
  pod_template_metadata = manifest["spec"]["replicatedJobs"][0]["template"][
      "spec"
  ]["template"]["metadata"]

  # Check annotations
  annotations = pod_template_metadata["annotations"]
  assert "existing-annotation" in annotations
  assert "devices.gke.io/container.tcpx-daemon" in annotations
  assert "networking.gke.io/default-interface" in annotations
  assert "networking.gke.io/interfaces" in annotations

  # Check tolerations
  tolerations = pod_template_spec["tolerations"]
  assert {
      "key": "user-workload",
      "operator": "Equal",
      "value": "true",
      "effect": "NoSchedule",
  } in tolerations

  # Check volumes
  volumes = pod_template_spec["volumes"]
  volume_names = {v["name"] for v in volumes}
  assert "libraries" in volume_names
  assert "sys" in volume_names
  assert "proc-sys" in volume_names
  assert "tcpx-socket" in volume_names
  assert "dshm" in volume_names

  # Check init container
  init_containers = pod_template_spec["initContainers"]
  assert len(init_containers) == 1
  tcpx_daemon = init_containers[0]
  assert tcpx_daemon["name"] == "tcpx-daemon"
  assert tcpx_daemon["image"].endswith(f":{tcpx_decorator.tcpx}")

  # Check GPU container update
  gpu_container = pod_template_spec["containers"][0]
  assert gpu_container["name"] == "main-gpu-container"

  # Check env
  env_vars = {e["name"]: e["value"] for e in gpu_container["env"]}
  assert env_vars["LD_LIBRARY_PATH"] == "/usr/local/nvidia/lib64"

  # Check volume mounts
  volume_mounts = {
      vm["name"]: vm["mountPath"] for vm in gpu_container["volumeMounts"]
  }
  assert volume_mounts["tcpx-socket"] == "/tmp"
  assert volume_mounts["libraries"] == "/usr/local/nvidia/lib64"
  assert volume_mounts["dshm"] == "/dev/shm"

  # Check non-GPU container is not updated
  sidecar_container = pod_template_spec["containers"][1]
  assert "env" not in sidecar_container
  assert "volumeMounts" not in sidecar_container


def test_decorate_job():
  """Tests decorate_job."""
  job_manifest = copy.deepcopy(BASE_JOB_MANIFEST)

  decorated_manifest = tcpx_decorator.decorate_job(job_manifest)
  pod_template_metadata = decorated_manifest["spec"]["template"]["metadata"]

  # Check annotations
  annotations = pod_template_metadata["annotations"]
  assert "existing-annotation" in annotations
  assert "devices.gke.io/container.tcpx-daemon" in annotations
  assert "networking.gke.io/default-interface" in annotations
  assert "networking.gke.io/interfaces" in annotations
