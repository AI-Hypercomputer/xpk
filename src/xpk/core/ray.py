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

from ..utils import write_tmp_file, xpk_print
from .commands import run_command_with_updates_retry


RAY_VERSION = '2.34.0'

ray_cluster_crd_yaml = """apiVersion: ray.io/v1
kind: RayCluster
metadata:
  name: raycluster
spec:
  rayVersion: '{version}'
  headGroupSpec:
    rayStartParams: {{}}
    #pod template
    template:
      spec:
        containers:
        - name: ray-head
          image: rayproject/ray:{version}
          resources:
            limits:
              cpu: 1
              memory: 2Gi
            requests:
              cpu: 500m
              memory: 2Gi
          ports:
          - containerPort: 6379
            name: gcs-server
          - containerPort: 8265 # Ray dashboard
            name: dashboard
          - containerPort: 10001
            name: client
  workerGroupSpecs:
    - replicas: {replicas} # TODO: Set min and max replicas
      numOfHosts: {num_hosts}
      minReplicas: {replicas}
      maxReplicas: {replicas}
      groupName: workergroup0
      rayStartParams:
        block: 'true'
      template:
        spec:
          containers:
            - name: ray-worker
              image: rayproject/ray:{version}
              resources:
                limits:
                  cpu: 1
                  google.com/tpu: {chips_per_vm}
                  memory: 40G
                requests:
                  cpu: 1
                  google.com/tpu: {chips_per_vm}
                  memory: 40G
          nodeSelector:
            cloud.google.com/gke-tpu-accelerator: {accelerator}
            cloud.google.com/gke-tpu-topology: {topology}
"""


def install_ray_cluster(args, system) -> int:
  """Install a RayCluster on the cluster

  Args:
    args: user provided arguments for running the command.
    system: system characteristics.

  Returns:
    0 if successful and 1 otherwise.
  """

  command = 'kubectl delete rayclusters --all'
  task = 'Deleting old RayCluster'
  retry_attempts = 1
  return_code = run_command_with_updates_retry(
      command, task, args, num_retry_attempts=retry_attempts
  )

  yml_string = ray_cluster_crd_yaml.format(
      accelerator=system.gke_accelerator,
      topology=system.topology,
      chips_per_vm=system.chips_per_vm,
      num_hosts=system.vms_per_slice,
      replicas=args.num_slices,
      version=RAY_VERSION,
  )

  tmp = write_tmp_file(yml_string)
  command = f'kubectl apply -f {str(tmp.file.name)}'
  task = 'Applying RayCluster'
  retry_attempts = 1
  return_code = run_command_with_updates_retry(
      command, task, args, num_retry_attempts=retry_attempts
  )
  if return_code != 0:
    xpk_print(f'{task} not successful.')
  return return_code
