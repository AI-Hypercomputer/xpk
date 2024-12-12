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

from ..utils.console import xpk_exit, xpk_print
from .core import (
    AcceleratorType,
    get_all_nodepools_programmatic,
    get_user_workload_container,
    zone_to_region,
)
from .system_characteristics import SystemCharacteristics

PathwaysExpectedInstancesMap = {
    'v6e': 'tpuv6e',
    'v5p': 'tpuv5',
    'v5litepod': 'tpuv5e',
    'v4': 'tpuv4',
    'v3': 'tpuv3',
}


def get_pathways_worker_args(args) -> str:
  """Arguments for the Pathways workers.
  Args:
    args: user provided arguments for running the command.

  Returns:
    str: yaml containing arguments for the Pathways workers.
  """
  yaml = """- --server_port=29001
              - --resource_manager_address={rm_address}
              - --temporary_flags_for_debugging=temporary_flag_for_debugging_megascale_address_derive_from_megascale_grpc=true
              - --megascale_grpc_premap_memory_bytes=17179869184
              - --gcs_scratch_location={args.pathways_gcs_location}
              - --megascale_graph_within_launch_hang_threshold=5"""  # More flags we can adjust here: https://source.corp.google.com/piper///depot/google3/platforms/xla/megascale/runtime/executor/executor.cc;l=53-81;rcl=705575633

  if args.use_pathways:
    return yaml.format(args=args, rm_address=get_rm_address(args))
  else:
    return ''


def get_pathways_proxy_args(args) -> str:
  """Arguments for the Pathways proxy.
  Args:
    args: user provided arguments for running the command.

  Returns:
    str: yaml containing arguments for the Pathways proxy.
  """
  yaml = """- --server_port=29000
              - --resource_manager_address={rm_address}
              - --xla_tpu_scoped_vmem_limit_kib=98304
              - --xla_tpu_enable_async_collective_fusion=true
              - --xla_tpu_enable_async_collective_fusion_fuse_all_gather=true
              - --xla_tpu_enable_async_collective_fusion_multiple_steps=true
              - --xla_tpu_overlap_compute_collective_tc=true
              - --xla_enable_async_all_gather=true
              - --xla_tpu_spmd_rng_bit_generator_unsafe=true
              - --xla_tpu_enable_sunk_dcn_allreduce_done_with_host_reduction=true
              - --gcs_scratch_location={args.pathways_gcs_location}"""

  if args.use_pathways:
    return yaml.format(args=args, rm_address=get_rm_address(args))
  else:
    return ''


def add_pw_resource_flavors(args):
  """Add resource flavors required for Pathways enabled clusters."""
  resource_flavor_yaml = """apiVersion: kueue.x-k8s.io/v1beta1
kind: ResourceFlavor
metadata:
  name: cpu-rm
spec:
  nodeLabels:
    cloud.google.com/gke-nodepool: cpu-rm-np
---
apiVersion: kueue.x-k8s.io/v1beta1
kind: ResourceFlavor
metadata:
  name: cpu-proxy
spec:
  nodeLabels:
    cloud.google.com/gke-nodepool: cpu-proxy-np
---
apiVersion: kueue.x-k8s.io/v1beta1
kind: ResourceFlavor
metadata:
  name: cpu-user
spec:
  nodeLabels:
    cloud.google.com/gke-nodepool: cpu-user-np
---"""
  if args.enable_pathways:
    return resource_flavor_yaml
  return ''


def add_pw_resources_to_kueue(args):
  """Add resource flavors required for Pathways, to the cluster queue."""
  resources_yaml = """- coveredResources: ["cpu", "memory"]
    flavors:
    - name: cpu-rm
      resources:
      - name: "cpu"
        nominalQuota: 480
      - name: "memory"
        nominalQuota: 2000G
    - name: cpu-proxy
      resources:
      - name: "cpu"
        nominalQuota: 480
      - name: "memory"
        nominalQuota: 2000G
    - name: cpu-user
      resources:
      - name: "cpu"
        nominalQuota: 480
      - name: "memory"
        nominalQuota: 2000G"""
  if args.enable_pathways:
    return resources_yaml
  return ''


def ensure_pathways_workload_prerequisites(args, system) -> bool:
  """Check all Pathways workload prerequisites and set necessary args.

  Args:
    args: user provided arguments for running the command.
    system: system characteristics.

  Returns:
    True once conditions satisfy and variables are set. Exits otherwise.
  """
  # Ensure command is provided if not using Pathways in headless mode
  if args.command is None and not args.headless:
    xpk_print(
        'Please provide a command using "--command" for the docker container to'
        ' execute. Command is not required if you wish to run Pathways'
        ' workloads in headless mode (`xpk workload create-pathways'
        ' --headless`).'
    )
    xpk_exit(1)

  # Ensure the cluster and CPU nodepools were created with create-pathways
  all_node_pools = get_all_nodepools_programmatic(args)
  desired_pw_cpu_node_pools = {'cpu-user-np', 'cpu-rm-np', 'cpu-proxy-np'}
  if not desired_pw_cpu_node_pools.issubset(set(all_node_pools[0])):
    xpk_print(
        'Cluster needs to be created with `xpk create-pathways` to run'
        ' Pathways workloads.'
    )
    xpk_exit(1)

  # Ensure device type is TPUs - currently Pathways supports TPUs only.
  if system.accelerator_type != AcceleratorType['TPU']:
    xpk_print('Currently, Pathways workloads can only be run on TPUs.')
    xpk_exit(1)

  # Set proxy address to be consumed in helper methods and displayed to user.
  args.pathways_proxy_address = get_proxy_address(args)

  # Set the job which determines the life of other Pathways jobs
  args.targetReplicatedJob = 'proxy' if args.headless else 'main'

  # Always report user code failures back to JobSet.
  args.restart_on_user_code_failure = True

  return True


def get_pathways_unified_query_link(args) -> str:
  """Get the unified query link for the pathways workload."""
  pw_suffixes = ['main', 'rm', 'proxy']
  pw_pod_names = [f'"{args.workload}-{suffix}-0"' for suffix in pw_suffixes]
  pw_pod_names_query = '%20OR%20'.join(pw_pod_names + ['worker-0-0'])
  query_params = (
      'resource.type%3D"k8s_container"%0A'
      f'resource.labels.project_id%3D"{args.project}"%0A'
      f'resource.labels.location%3D"{zone_to_region(args.zone)}"%0A'
      f'resource.labels.cluster_name%3D"{args.cluster}"%0A'
      f'resource.labels.pod_name:{pw_pod_names_query}%0A'
      'severity>%3DDEFAULT'
  )

  return f'https://console.cloud.google.com/logs/query;query={query_params}'


def get_pathways_rm_args(args, system: SystemCharacteristics) -> str:
  """Arguments for the Pathways resource manager.
  Args:
    args: user provided arguments for running the command.

  Returns:
    str: yaml containing arguments for the Pathways resource manager.
  """
  yaml = """- --server_port=29001
              - --gcs_scratch_location={args.pathways_gcs_location}
              - --node_type=resource_manager
              - --instance_count={instance_count}
              - --temporary_flags_for_debugging=temporary_flag_for_debugging_worker_expected_tpu_chip_config=megachip;;;temporary_flag_for_debugging_megascale_address_derive_from_megascale_grpc=true
              - --instance_type={instance_type}"""
  if args.use_pathways:
    return yaml.format(
        args=args,
        instance_count=args.num_slices,
        instance_type=f'{get_pathways_expected_tpu_type(system.device_type)}:{system.topology}',
    )
  else:
    return ''


def get_user_workload_for_pathways(args, system: SystemCharacteristics) -> str:
  """
  Create a user workload container for Pathways.
  Don't create one for Pathways headless mode.

  Args:
    args: user provided args.
    system: system characteristics.


  Returns:
    str:
      Pathways server port as a YAML string
  """
  user_workload_yaml = """- name: main
    replicas: 1
    template:
      metadata:
        labels:
          xpk.google.com/workload: {args.workload}
      spec:
        backoffLimit: 0
        completions: 1
        parallelism: 1
        template:
          spec:
            containers:
              {container}
            nodeSelector:
              cloud.google.com/gke-nodepool: cpu-user-np
            hostNetwork: true
              dnsPolicy: ClusterFirstWithHostNet
            restartPolicy: OnFailure
            hostNetwork: true
            dnsPolicy: ClusterFirstWithHostNet
            volumes:
            - hostPath:
                path: /tmp
                type: DirectoryOrCreate
              name: shared-tmp"""
  if args.headless:
    return ''
  else:
    container, _ = get_user_workload_container(args, system)
    return user_workload_yaml.format(args=args, container=container)


def get_rm_address(args) -> str:
  """Generates the Pathways resource manager address.
  Args:
    args: user provided arguments for running the command.

  Returns:
    str: Fully qualified RM address.
  """
  rm_address = f'{args.workload}-rm-0-0.{args.workload}:29001'
  return rm_address


def get_proxy_address(args) -> str:
  """Generates the Pathways proxy address.
  Args:
    args: user provided arguments for running the command.

  Returns:
    str: Fully qualified proxy address.
  """
  proxy_address = f'grpc://{args.workload}-proxy-0-0.{args.workload}:29000'
  return proxy_address


def get_pathways_expected_tpu_type(device_type: str) -> str:
  """Returns the device type expected by Pathways
  Args:
    device_type: the system characteristic device type

  Returns:
    str: the device type expected by pathways.
  """
  raw_type = device_type.split('-')[0].lower()
  pathways_expected_instance = PathwaysExpectedInstancesMap[raw_type]
  if not pathways_expected_instance:
    xpk_print(
        f'Passed in device_type {device_type} is incorrect. Please pass in a'
        ' valid device type'
    )
    xpk_exit(1)
  return pathways_expected_instance
