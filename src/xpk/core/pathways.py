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

from ..core.commands import run_command_for_value, run_command_with_updates, run_commands
from ..core.docker_container import get_user_workload_container
from ..core.gcloud_context import zone_to_region
from ..core.nodepool import get_all_nodepools_programmatic
from ..utils.console import xpk_exit, xpk_print
from .config import AcceleratorType
from .system_characteristics import SystemCharacteristics


def add_pw_resource_flavors(args):
  """Add resource flavors required for Pathways enabled clusters."""
  resource_flavor_yaml = """apiVersion: kueue.x-k8s.io/v1beta1
kind: ResourceFlavor
metadata:
  name: cpu-user
spec:
  nodeLabels:
    cloud.google.com/gke-nodepool: cpu-np
---"""
  if args.enable_pathways:
    return resource_flavor_yaml
  return ''


def add_pw_resources_to_kueue(args):
  """Add resource flavors required for Pathways, to the cluster queue."""
  resources_yaml = """- coveredResources: ["cpu", "memory"]
    flavors:
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
  # Ensure that PathwaysJob is installed and available on the cluster.
  if not check_if_pathways_job_is_installed(args):
    xpk_exit(1)

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
  desired_pw_cpu_node_pools = {'cpu-np'}
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


def check_if_pathways_job_is_installed(args) -> bool:
  """Check if PathwaysJob is installed on the cluster.
  Args:
    args: user provided arguments for running the command.
  Returns:
    0 if successful and 1 otherwise.
  """
  command = (
      'kubectl get pods -n pathways-job-system --no-headers -o'
      ' custom-columns=NAME:.metadata.name'
  )
  task = f'Check if PathwaysJob is installed on {args.cluster}'
  return_code, return_msg = run_command_for_value(command, task, args)
  # return_msg contains the name of the controller pod, if found.
  xpk_print('check_if_pathways_job_is_installed', return_code, return_msg)

  if return_code != 0:
    xpk_print(f'{task} returned with ERROR {return_code}.\n')
    return False
  if not return_msg:
    xpk_print(
        'You are using a new version of XPK, which uses PathwaysJob'
        ' for Pathways workloads. Please update the cluster using'
        ' `cluster create-pathways` to enjoy the upgrade!'
    )
    return False
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


def append_custom_pathways_flags(custom_args, prev_indentation=8) -> str:
  """Append custom Pathways args to Pathways components using a YAML with proper indentation.

  Returns:
    yaml (string): yaml with additional args appended.
  """
  yaml = """"""
  indentation = ' ' * (prev_indentation + 2)
  if custom_args:
    custom_args = custom_args.split(' ')
    for arg in custom_args:
      yaml += '\n' + indentation + '- ' + arg
  return yaml


def append_custom_pathways_proxy_server(args) -> str:
  """Append custom Pathways proxy server component using a YAML with proper indentation.

  Returns:
      yaml (string): yaml with custom proxy server appended.
  """
  yaml = """"""
  if args.proxy_server_image or args.custom_pathways_proxy_server_args:
    yaml = """- componentType: proxy_server"""
  indentation = (
      ' ' * 8
  )  # Currently 8, based on the YAML, may need to update in the future.
  if args.proxy_server_image:
    yaml += '\n' + indentation + 'image: ' + args.proxy_server_image
  if args.custom_pathways_proxy_server_args:
    yaml += '\n' + indentation + 'customFlags: '
    yaml += append_custom_pathways_flags(
        args.custom_pathways_proxy_server_args, len(indentation)
    )
  return yaml


def append_custom_pathways_server(args) -> str:
  """Append custom Pathways server component using a YAML with proper indentation.

  Returns:
      yaml (string): yaml with custom pathways server appended.
  """
  yaml = """"""
  if args.server_image or args.custom_pathways_server_args:
    yaml = """- componentType: pathways_server"""
  indentation = (
      ' ' * 8
  )  # Currently 8, based on the YAML, may need to update in the future.
  if args.server_image:
    yaml += '\n' + indentation + 'image: ' + args.server_image
  if args.custom_pathways_server_args:
    yaml += '\n' + indentation + 'customFlags: '
    yaml += append_custom_pathways_flags(
        args.custom_pathways_server_args, len(indentation)
    )
  return yaml


def append_custom_pathways_worker(args) -> str:
  """Append custom Pathways worker component using a YAML with proper indentation.

  Returns:
      yaml (string): yaml with custom pathways server appended.
  """
  yaml = """"""
  if args.server_image or args.custom_pathways_worker_args:
    yaml = """- componentType: pathways_worker"""
  indentation = (
      ' ' * 8
  )  # Currently 8, based on the YAML, may need to update in the future.
  if args.server_image:
    yaml += '\n' + indentation + 'image: ' + args.server_image
  if args.custom_pathways_worker_args:
    yaml += '\n' + indentation + 'customFlags: '
    yaml += append_custom_pathways_flags(
        args.custom_pathways_worker_args, len(indentation)
    )
  return yaml


def append_custom_colocated_python_sidecar(args) -> str:
  """Append custom Pathways colocated python sidecar component using a YAML with proper indentation.

  Returns:
      yaml (string): yaml with custom pathways server appended.
  """
  yaml = """"""
  if args.colocated_python_sidecar_image:
    yaml = """- componentType: colocated_python_sidecar"""
    indentation = (
        ' ' * 8
    )  # Currently 8, based on the YAML, may need to update in the future.
    yaml += '\n' + indentation + 'image: ' + args.colocated_python_sidecar_image
  return yaml


def get_user_workload_for_pathways(
    args,
    system: SystemCharacteristics,
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
  user_workload_yaml = """
          metadata:
          spec:
            containers:
              {container}
            nodeSelector:
              cloud.google.com/gke-nodepool: cpu-np
            hostNetwork: true
            dnsPolicy: ClusterFirstWithHostNet
            restartPolicy: Never
            volumes:
            - hostPath:
                path: /tmp
                type: DirectoryOrCreate
              name: shared-tmp
    """
  if args.headless:
    return ''
  else:
    container, _ = get_user_workload_container(args, system)
    return user_workload_yaml.format(
        args=args,
        container=container,
    )


def get_proxy_address(args) -> str:
  """Generates the Pathways proxy address.
  Args:
    args: user provided arguments for running the command.

  Returns:
    str: Fully qualified proxy address.
  """
  proxy_address = (
      f'grpc://{args.workload}-pathways-head-0-0.{args.workload}:29000'
  )
  return proxy_address


def try_to_delete_pathwaysjob_first(args, workloads) -> bool:
  """Function to delete PathwaysJob workload. This is needed as PathwaysJob
  owns the JobSet it creates.

  Args:
    args: user provided arguments for running the command.
    workloads: list of workloads that match the delete filter.

  Returns:
    True if successful and False otherwise.
  """
  commands = []
  task_names = []
  for workload in workloads:
    args.workload = workload
    command = f'kubectl delete pathwaysjob {workload} -n default'
    task_name = f'PathwaysWorkloadDelete-{workload}'
    commands.append(command)
    task_names.append(task_name)

  # Not batching deletion for single workload
  if len(workloads) == 1:
    return_code = run_command_with_updates(commands[0], 'Delete Workload', args)
  else:
    return_code = run_commands(
        commands, 'Delete Workload', task_names, batch=100
    )

  if return_code != 0:
    xpk_print(f'Delete Workload request returned ERROR {return_code}')
    return False
  return True
