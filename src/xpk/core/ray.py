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

import re
from ..utils.console import xpk_exit, xpk_print
from ..utils.file import write_tmp_file
from .commands import run_command_for_value, run_command_with_updates_retry


HEAD_CPU = 0.5
WORKER_CPU = 0.9
GCS_SERVER = 6379
DASHBOARD = 8265
CLIENT = 10001
MULTISLICE = 8081

ray_cluster_crd_yaml = """apiVersion: v1
kind: Namespace
metadata:
  name: ray
---
apiVersion: ray.io/v1
kind: RayCluster
metadata:
  name: raycluster
  namespace: ray
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
              cpu: {head_cpu}
              memory: {head_mem}
            requests:
              cpu: {head_cpu}
              memory: {head_mem}
          ports:
          - containerPort: {gcs_server}
            name: gcs-server
          - containerPort: {dashboard} # Ray dashboard
            name: dashboard
          - containerPort: {client}
            name: client
          - containerPort: {multislice}
            name: multislice
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
                  cpu: {worker_cpu}
                  google.com/tpu: {chips_per_vm}
                  memory: {worker_mem}
                requests:
                  cpu: {worker_cpu}
                  google.com/tpu: {chips_per_vm}
                  memory: {worker_mem}
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

  delete_ray_cluster(args)

  label = 'cloud.google.com/gke-nodepool=default-pool'
  available_head_cpu, available_head_mem = generate_available_resources(
      label, args, HEAD_CPU
  )

  label = f'cloud.google.com/gke-tpu-accelerator={system.gke_accelerator}'
  available_worker_cpu, available_worker_mem = generate_available_resources(
      label, args, WORKER_CPU
  )

  yml_string = ray_cluster_crd_yaml.format(
      accelerator=system.gke_accelerator,
      topology=system.topology,
      chips_per_vm=system.chips_per_vm,
      num_hosts=system.vms_per_slice,
      replicas=args.num_slices,
      version=args.ray_version,
      worker_cpu=available_worker_cpu,
      worker_mem=available_worker_mem,
      head_cpu=available_head_cpu,
      head_mem=available_head_mem,
      gcs_server=GCS_SERVER,
      dashboard=DASHBOARD,
      client=CLIENT,
      multislice=MULTISLICE,
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
    xpk_exit(return_code)
  return return_code


def delete_ray_cluster(args) -> None:
  """Delete all RayClusters on the cluster

  Args:
    args: user provided arguments for running the command.

  Returns:
    None
  """

  command = 'kubectl delete rayclusters -n ray --all'
  task = 'Deleting old RayCluster'
  retry_attempts = 1
  return_code = run_command_with_updates_retry(
      command, task, args, num_retry_attempts=retry_attempts
  )

  if return_code != 0:
    xpk_print(f'{task} not successful.')
    xpk_exit(return_code)

  return


def generate_available_resources(label, args, percent) -> tuple:
  """Generate the available resources for the nodes that match the given label

  Args:
    label: the label used to match the appropriate nodes
    args: user provided arguments for running the command
    percent: the percent of the available resources to use

  Returns:
    A tuple with the available cpu and memory
  """

  command = (
      f"kubectl get nodes -l {label} -o jsonpath='{{.items[0].metadata.name}}'"
  )
  task = f'Getting nodes with label {label}'
  _, node_name = run_command_for_value(command, task, args)

  command = (
      f"kubectl get node {node_name} -o jsonpath='{{.status.allocatable.cpu}}'"
  )
  task = 'Fetching available CPU on node'
  _, available_cpu = run_command_for_value(command, task, args)
  match = re.match(r'(\d+)([a-zA-Z]+)', available_cpu)
  if not match:
    xpk_print(
        'Could not find a regex match for allocatable cpu on TPU node'
        f' {node_name}'
    )
    xpk_exit(1)
  value, units = match.group(1), match.group(2)
  cpu_value = int(int(value) * percent)
  adjusted_available_cpu = str(cpu_value) + units

  command = (
      f'kubectl get node {node_name} -o'
      " jsonpath='{.status.allocatable.memory}'"
  )
  task = 'Fetching available memory on node'
  _, available_memory = run_command_for_value(command, task, args)
  match = re.match(r'(\d+)([a-zA-Z]+)', available_memory)
  if not match:
    xpk_print(
        'Could not find a regex match for allocatable memory on TPU node'
        f' {node_name}'
    )
    xpk_exit(1)
  value, units = match.group(1), match.group(2)
  memory_value = int(int(value) * percent)
  adjusted_available_memory = str(memory_value) + units

  return adjusted_available_cpu, adjusted_available_memory
