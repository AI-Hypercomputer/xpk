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

from .cluster import XPK_SA
from ..core.docker_container import get_user_workload_container
from ..core.gcloud_context import zone_to_region
from ..core.nodepool import get_all_nodepools_programmatic
from ..utils.console import xpk_exit, xpk_print
from .config import AcceleratorType
from .storage import Storage, get_storage_volumes_yaml, GCS_FUSE_ANNOTATION
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
                - --gcs_scratch_location={args.pathways_gcs_location}"""
  if args.use_pathways:
    if args.custom_pathways_worker_args:
      yaml = append_custom_pathways_args(yaml, args.custom_pathways_worker_args)
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
                - --gcs_scratch_location={args.pathways_gcs_location}"""

  if args.use_pathways:
    if args.custom_pathways_proxy_server_args:
      yaml = append_custom_pathways_args(
          yaml, args.custom_pathways_proxy_server_args
      )
    return yaml.format(args=args, rm_address=get_rm_address(args))
  else:
    return ''


def get_pathways_sidecar_container(args) -> str:
  """This is a sidecar container that runs the remote python server.

      It is a special case of the initContainer (designated by restartPolicy:
      Always)
      See https://kubernetes.io/docs/concepts/workloads/pods/sidecar-containers/
      for more details.
  Args:
    args: user provided arguments for running the command.

  Returns:
    str: yaml containing arguments for the Pathways sidecar container.
  """
  yaml = """initContainers:
              - name: remote-python-sidecar
                image: {args.remote_python_sidecar_image}
                imagePullPolicy: Always
                securityContext:
                  privileged: true
                volumeMounts:
                - mountPath: /tmp  # Shared volume mount with the main container.
                  name: shared-tmp
                restartPolicy: Always
                ports:
                - containerPort: 50051
                env:
                - name: GRPC_SERVER_ADDRESS
                  value: '0.0.0.0:50051'"""
  if args.use_pathways and args.remote_python_sidecar_image is not None:
    return yaml.format(args=args)
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

  return True


def get_pathways_unified_query_link(args) -> str:
  """Get the unified query link for the pathways workload."""
  query_params = (
      'resource.type%3D"k8s_container"%0A'
      f'resource.labels.project_id%3D"{args.project}"%0A'
      f'resource.labels.location%3D"{zone_to_region(args.zone)}"%0A'
      f'resource.labels.cluster_name%3D"{args.cluster}"%0A'
      f'resource.labels.pod_name:"{args.workload}-"%0A'
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
                - --instance_type={instance_type}"""
  if args.use_pathways:
    if args.custom_pathways_server_args:
      yaml = append_custom_pathways_args(yaml, args.custom_pathways_server_args)
    return yaml.format(
        args=args,
        instance_count=args.num_slices,
        instance_type=f'{get_pathways_expected_tpu_type(system.device_type)}:{system.topology}',
    )
  else:
    return ''


def append_custom_pathways_args(yaml, custom_args) -> str:
  """Append custom Pathways args to the YAML with proper indentation.

  Args:
      yaml (string): existing yaml containing args

  Returns:
      yaml (string): yaml with additional args appended.
  """
  second_line = yaml.split('\n')[1]
  if (
      not second_line
  ):  # to cover edge case if only one arg remains, we would have to look at the entire YAML in this case.
    return yaml
  # Calculate the indentation based on the second line of existing YAML.
  indentation = ' ' * (len(second_line) - len(second_line.lstrip()))
  custom_args = custom_args.split(' ')
  for arg in custom_args:
    yaml += '\n' + indentation + '- ' + arg
  return yaml


def get_user_workload_for_pathways(
    args,
    system: SystemCharacteristics,
    pod_failure_policy,
    storages: list[Storage],
) -> str:
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
          {pod_failure_policy}
          template:
            metadata:
              annotations:
                {gcs_fuse_annotation}
            spec:
              containers:
              {container}
              serviceAccountName: {service_account}
              nodeSelector:
                cloud.google.com/gke-nodepool: cpu-user-np
              hostNetwork: true
              dnsPolicy: ClusterFirstWithHostNet
              restartPolicy: Never
              volumes:
              - hostPath:
                  path: /tmp
                  type: DirectoryOrCreate
                name: shared-tmp
              {storage_volumes}"""
  if args.headless:
    return ''
  else:
    container, _ = get_user_workload_container(args, system)
    storage_volumes = get_storage_volumes_yaml(storages)
    return user_workload_yaml.format(
        args=args,
        container=container,
        storage_volumes=storage_volumes,
        pod_failure_policy=pod_failure_policy,
        service_account=XPK_SA,
        gcs_fuse_annotation=GCS_FUSE_ANNOTATION,
    )


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
