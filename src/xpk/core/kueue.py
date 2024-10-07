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
from .commands import run_command_with_updates_retry, run_command_for_value
from .core import (
    AutoprovisioningConfig,
    create_accelerator_label,
    create_machine_label,
    get_total_chips_requested_from_args,
)
from .pathways import add_pw_resource_flavors, add_pw_resources_to_kueue
from .system_characteristics import (
    AcceleratorTypeToAcceleratorCharacteristics,
    SystemCharacteristics,
)
from sys import platform
from platform import machine
CLUSTER_QUEUE_NAME = 'cluster-queue'
LOCAL_QUEUE_NAME = 'multislice-queue'


cluster_set_crd_yaml = """apiVersion: kueue.x-k8s.io/v1beta1
kind: ResourceFlavor
metadata:
  name: {cluster_hardware_name}
spec:
  nodeLabels:
    {accelerator_label}
    {machine_label}
---
{pw_resource_flavors}
apiVersion: kueue.x-k8s.io/v1beta1
kind: ClusterQueue
metadata:
  name: {cluster_queue_name}
spec:
  preemption:
      reclaimWithinCohort: Never # Don't preempt other queues in the cohort.
      withinClusterQueue: LowerPriority
  namespaceSelector: {{}} # match all.
  resourceGroups:
  {covered_resources_config}
  {pw_resources_kueue}
---
apiVersion: kueue.x-k8s.io/v1beta1
kind: LocalQueue
metadata:
  namespace: default
  name: {local_queue_name}
spec:
  clusterQueue: {cluster_queue_name}
---
apiVersion: scheduling.k8s.io/v1
kind: PriorityClass
metadata:
  name: very-low
value: 100
globalDefault: false
description: "Very Low"
---
apiVersion: scheduling.k8s.io/v1
kind: PriorityClass
metadata:
  name: low
value: 250
globalDefault: false
description: "Low"
---
apiVersion: scheduling.k8s.io/v1
kind: PriorityClass
metadata:
  name: medium
value: 500
globalDefault: false
description: "Medium"
---
apiVersion: scheduling.k8s.io/v1
kind: PriorityClass
metadata:
  name: high
value: 750
globalDefault: false
description: "High"
---
apiVersion: scheduling.k8s.io/v1
kind: PriorityClass
metadata:
  name: very-high
value: 1000
globalDefault: false
description: "Very High"
"""

cluster_preheat_yml = """
apiVersion: apps/v1
kind: DaemonSet
metadata:
  name: {cachekey}
  labels:
    k8s-app: {cachekey}
spec:
  selector:
    matchLabels:
      k8s-app: {cachekey}
  updateStrategy:
    type: RollingUpdate
  template:
    metadata:
      labels:
        name: {cachekey}
        k8s-app: {cachekey}
    spec:
      affinity:
        nodeAffinity:
          requiredDuringSchedulingIgnoredDuringExecution:
            nodeSelectorTerms:
            - matchExpressions:
              - key: {nodeSelectorKey}
                operator: Exists
      tolerations:
      - operator: "Exists"
      containers:
      - image: {image_name}
        name: {cachekey}
        command: [ "sleep", "inf" ]
"""

def verify_kueuectl_installation(args) -> int:
  """Verify if if kueuectl is installed.
  Args:
    args: user provided arguments for running the command.
  Returns:
    0 if kueuectl installed and error code otherwise.
  """
  command = (
      'kubectl kueue version'
  )
  task = 'Verify kueuectl installation on cluster'
  return_code, _ = run_command_for_value(command, task, args)
  if return_code != 0:
    xpk_print(f'{task} returned ERROR {return_code}')
  return return_code

def get_system_spec() -> tuple[str, str]:
  """Get operating system and machine type

  Returns:
    tuple of strings in format (operating system, machine type).
  """
  os = platform
  machine_type = machine()
  return os, machine_type


def get_kueuectl_installation_command(system, machine_type) -> list[str]:
  """Create command for installing kueuectl depending on operating system and machine type.
  Function execution moves to /usr/local/bin/, therefore sudo is needed.
  Args:
    system: operating system, supported values are [darwin, linux].
    machine_type: machine type, supported values are [x86_64, arm].
  Returns
    List of commands to download kueuectl.

  """
  curl = ''
  if system == 'darwin' and 'x86_64' in machine_type:
    curl += 'curl -Lo ./kubectl-kueue https://github.com/kubernetes-sigs/kueue/releases/download/v0.8.1/kubectl-kueue-darwin-amd64'
  if system == 'darwin' and 'arm' in machine_type:
    curl += 'curl -Lo ./kubectl-kueue https://github.com/kubernetes-sigs/kueue/releases/download/v0.8.1/kubectl-kueue-darwin-arm64'
  if system == 'linux' and 'arm' in machine_type:
    curl += 'curl -Lo ./kubectl-kueue https://github.com/kubernetes-sigs/kueue/releases/download/v0.8.1/kubectl-kueue-linux-arm64'
  if system == 'linux' and 'x86_64' in machine_type:
    curl += 'curl -Lo ./kubectl-kueue https://github.com/kubernetes-sigs/kueue/releases/download/v0.8.1/kubectl-kueue-linux-amd64'  

  chmod = 'chmod +x ./kubectl-kueue'
  mv = 'sudo mv ./kubectl-kueue /usr/local/bin/kubectl-kueue'

  return [curl, chmod , mv]

def install_kueuectl(args) -> int:
  """Install Kueuectl on the cluster

  Args:
    args: user provided arguments for running the command.

  Returns:
    0 if successful and 1 otherwise.
  """
  
  system, machine_type = get_system_spec()
  commands = get_kueuectl_installation_command(system, machine_type)
  
  task = 'Install kueuectl on cluster'
  for command in commands:
    return_code, _ = run_command_for_value(command, task, args)
    if return_code != 0:
      xpk_print(f'{task} returned ERROR {return_code}')
  return return_code


def install_kueue_on_cluster(args) -> int:
  """Install Kueue on the cluster.

  Args:
    args: user provided arguments for running the command.

  Returns:
    0 if successful and 1 otherwise.
  """
  command = (
      'kubectl apply --server-side --force-conflicts -f'
      ' https://github.com/kubernetes-sigs/kueue/releases/download/v0.6.1/manifests.yaml'
  )
  task = 'Set Kueue On Cluster'
  return_code = run_command_with_updates_retry(command, task, args)
  if return_code != 0:
    xpk_print(f'{task} returned ERROR {return_code}')
  return return_code


def enable_kueue_credentials(
    args,
    system: SystemCharacteristics,
    autoprovisioning_config: AutoprovisioningConfig | None,
) -> int:
  """Enable Kueue credentials.

  Args:
    args: user provided arguments for running the command.
    system: system level arguments.
    autoprovisioning_config: Autoprovisioning config to configure kueue with if
        autoprovisioning is enabled.

  Returns:
    0 if successful and 1 otherwise.
  """
  device_type = system.device_type
  cluster_hardware_name = f'{args.num_slices}x{device_type}'
  resource_type = AcceleratorTypeToAcceleratorCharacteristics[
      system.accelerator_type
  ].resource_type

  autoprovisioning_enabled = False
  if autoprovisioning_config:
    # Determine total resources available based on autoprovisioning max chips.
    autoprovisioning_enabled = True
    total_chips = autoprovisioning_config.maximum_chips
    cluster_hardware_name = f'{system.gke_accelerator}'
  else:
    # Determine total chips based on user specified topology.
    total_chips = get_total_chips_requested_from_args(args, system)

  covered_resources_config = get_kueue_covered_resources_config(
      cluster_hardware_name=cluster_hardware_name,
      resource_type=resource_type,
      total_chips=total_chips,
  )
  yml_string = cluster_set_crd_yaml.format(
      system=system,
      cluster_hardware_name=cluster_hardware_name,
      accelerator_label=create_accelerator_label(
          system.accelerator_type, system
      ),
      machine_label=create_machine_label(
          system.accelerator_type, system, autoprovisioning_enabled
      ),
      covered_resources_config=covered_resources_config,
      resource_type=AcceleratorTypeToAcceleratorCharacteristics[
          system.accelerator_type
      ].resource_type,
      pw_resource_flavors=add_pw_resource_flavors(args),
      pw_resources_kueue=add_pw_resources_to_kueue(args),
      cluster_queue_name=CLUSTER_QUEUE_NAME,
      local_queue_name=LOCAL_QUEUE_NAME,
  )

  tmp = write_tmp_file(yml_string)
  command = f'kubectl apply -f {str(tmp.file.name)}'
  # For kueue setup, we see a timeout error due to the webhook not
  # being ready. Let's retry and wait a few seconds.
  task = 'Applying Kueue Credentials'
  retry_attempts = 3
  return_code = run_command_with_updates_retry(
      command, task, args, num_retry_attempts=retry_attempts
  )
  if return_code != 0:
    # We have seen some scenarios where credentials need a few minutes for kueue
    # and jobset installation to be ready before credentials can be applied.
    # As a workaround we will retry again with longer wait times.
    retry_wait_seconds = 60
    xpk_print(
        f'{task} still not successful. Retrying {retry_attempts} more timeswith'
        f' increased wait time of {retry_wait_seconds} seconds between tries.'
        ' Kueue Credentials need Kueue system to be ready which can take some'
        ' time.'
    )
    return_code = run_command_with_updates_retry(
        command=command,
        task=task,
        args=args,
        num_retry_attempts=retry_attempts,
        wait_seconds=retry_wait_seconds,
    )
    if return_code != 0:
      xpk_print(f'{task} returned ERROR {return_code}')
  return return_code


def get_kueue_covered_resources_config(
    cluster_hardware_name, resource_type, total_chips
) -> str:
  """Gets Kueue covered resources configuration.

  Args:
    cluster_hardware_name: cluster hardware name.
    resource_type: resource type of tpu or gpu.
    total_chips: total number of chips for the specific resource type.

  Returns:
    A string of Kueue covered resources configuration.
  """
  config_format = """
  - coveredResources: ["{resource_type}"]
    flavors:
    - name: {cluster_hardware_name}
      resources:
      - name: "{resource_type}"
        nominalQuota: {total_chips}
  """
  config_string = config_format.format(
      cluster_hardware_name=cluster_hardware_name,
      resource_type=resource_type,
      total_chips=total_chips,
  )
  return config_string
