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

from ..core.cluster import get_cluster_credentials
from ..core.commands import run_command_for_value
from ..core.gcloud_context import add_zone_and_project, zone_to_region
from ..core.kueue import CLUSTER_QUEUE_NAME, LOCAL_QUEUE_NAME
from ..core.resources import CLUSTER_METADATA_CONFIGMAP, CLUSTER_RESOURCES_CONFIGMAP
from ..utils.console import xpk_exit, xpk_print
from ..utils.file import append_tmp_file, write_tmp_file
from .workload import get_workload_list


def inspector_run_command_helper(
    args, command, command_description, file
) -> int:
  """Runs a command for xpk inspector, and build the output file.

  Args:
    args: user provided arguments for running the command.
    command: the cli command to run.
    command_description: a brief description of the command run.
    file: file to add command output to.

  Returns:
    0 if successful and 1 otherwise.
  """
  prefix = f'Command: {command}\nCommand Description: {command_description}\n'
  postfix = '========================================================'
  return_code, command_output = run_command_for_value(
      command, f'{command_description}', args
  )

  if return_code != 0:
    xpk_print(
        f'{command} returned ERROR {return_code} with output: {command_output}'
    )
    return 1

  inspector_command_output = f'{prefix} \n{command_output} \n{postfix} \n'
  append_tmp_file(inspector_command_output, file)

  if args.print_to_terminal:
    xpk_print(inspector_command_output)
  return 0


def inspector_run_workload_list_helper(args, command_description, file) -> int:
  """Runs a workload list command for xpk inspector, and build the output file.

  Args:
    args: user provided arguments for running the command.
    command_description: a brief description of the command run.
    file: file to add command output to.

  Returns:
    0 if successful and 1 otherwise.
  """
  prefix = f'Command Description: {command_description}\n'
  postfix = '========================================================'
  return_code, command_output = get_workload_list(args)
  if return_code != 0:
    xpk_exit(return_code)
  inspector_command_output = f'{prefix} \n{command_output} \n{postfix} \n'
  append_tmp_file(inspector_command_output, file)
  if args.print_to_terminal:
    xpk_print(inspector_command_output)
  return 0


def inspector_output_link_helper(args, link, link_description, file) -> int:
  """Outputs a link for xpk inspector to the output file.

  Args:
    args: user provided arguments for.
    link: link to output.
    link_description: describes what the link is for.
    file: file to add command output to.

  Returns:
    0 if successful and 1 otherwise.
  """
  inspector_link = (
      f'Link Description: {link_description}\n'
      f'Link: {link}\n'
      '========================================================'
  )
  append_tmp_file(inspector_link, file)
  if args.print_to_terminal:
    xpk_print(inspector_link)
  return 0


def inspector(args) -> None:
  """Function around inspector which investigates failures in the kueue.

  Args:
    args: user provided arguments for running the command.

  Returns:
    0 if successful and 1 otherwise.
  """
  # Future Improvements for inspector:
  # 2. List what is next in Queue.
  # 3. Split inspector into different subcommands to parse info easier.

  final_return_code = 0
  xpk_print(args)

  add_zone_and_project(args)
  get_cluster_credentials(args)

  inspector_file = write_tmp_file(
      '==================\nXPK inspector OUTPUT:\n==================\n'
  )
  command_and_descriptions = [
      ('gcloud version', 'Local Setup: gcloud version'),
      (
          (
              'gcloud config get project; gcloud config get compute/zone;'
              ' gcloud config get compute/region'
          ),
          'Local Setup: Project / Zone / Region',
      ),
      (
          (
              'gcloud beta container clusters list --project'
              f' {args.project} --region {zone_to_region(args.zone)} | grep -e'
              f' NAME -e {args.cluster}'
          ),
          'GKE: Cluster Details',
      ),
      (
          (
              'kubectl get configmap'
              f' {args.cluster}-{CLUSTER_METADATA_CONFIGMAP} -o yaml'
          ),
          'GKE: Cluster Metadata ConfigMap Details',
      ),
      (
          (
              'kubectl get configmap'
              f' {args.cluster}-{CLUSTER_RESOURCES_CONFIGMAP} -o yaml'
          ),
          'GKE: Cluster Resources ConfigMap Details',
      ),
      (
          (
              f'gcloud beta container node-pools list --cluster {args.cluster} '
              f' --project={args.project} --region={zone_to_region(args.zone)}'
          ),
          'GKE: Node pool Details',
      ),
      (
          (
              "kubectl get node -o custom-columns='NODE_NAME:metadata.name,"
              ' READY_STATUS:.status.conditions[?(@.type=="Ready")].status,'
              " NODEPOOL:metadata.labels.cloud\\.google\\.com/gke-nodepool'"
          ),
          'Kubectl: All Nodes',
      ),
      (
          (
              'kubectl get node -o'
              " custom-columns=':metadata.labels.cloud\\.google\\.com/gke-nodepool'"
              ' | sort | uniq -c'
          ),
          'Kubectl: Number of Nodes per Node Pool',
      ),
      (
          (
              "kubectl get node -o custom-columns='NODE_NAME:metadata.name,"
              ' READY_STATUS:.status.conditions[?(@.type=="Ready")].status,'
              " NODEPOOL:metadata.labels.cloud\\.google\\.com/gke-nodepool' |"
              " grep -w True | awk {'print $3'} | sort | uniq -c"
          ),
          'Kubectl: Healthy Node Count Per Node Pool',
      ),
      (
          f'kubectl describe ClusterQueue {CLUSTER_QUEUE_NAME}',
          'Kueue: ClusterQueue Details',
      ),
      (
          f'kubectl describe LocalQueue {LOCAL_QUEUE_NAME}',
          'Kueue: LocalQueue Details',
      ),
      ('kubectl describe ResourceFlavor', 'Kueue: ResourceFlavor Details'),
      (
          (
              'kubectl describe Deployment kueue-controller-manager -n'
              ' kueue-system'
          ),
          'Kueue: Kueue Deployment Details',
      ),
      (
          (
              'kubectl describe Deployment jobset-controller-manager -n'
              ' jobset-system'
          ),
          'Jobset: Deployment Details',
      ),
      (
          (
              'kubectl logs deployment/kueue-controller-manager -n kueue-system'
              ' --tail=100 --prefix=True'
          ),
          'Kueue Manager Logs',
      ),
      (
          (
              'kubectl logs deployment/jobset-controller-manager -n'
              ' jobset-system --tail=100 --prefix=True'
          ),
          'Jobset Manager Logs',
      ),
  ]

  for command, description in command_and_descriptions:
    return_code = inspector_run_command_helper(
        args, command, description, inspector_file
    )
    if return_code != 0:
      final_return_code = return_code
      xpk_print(
          f'inspector failed in command: {command} description:'
          f' {description} return code: {return_code}'
      )

  # Workload list views:
  filter_by_statuses = ['EVERYTHING', 'QUEUED', 'RUNNING']
  for filter_by_status in filter_by_statuses:
    args.filter_by_job = None
    args.filter_by_status = filter_by_status
    command_description = (
        f'xpk workload list --filter-by-status={args.filter_by_status}'
        f' --filter-by-job={args.filter_by_job} --project={args.project} --zone={args.zone}'
        f' --cluster={args.cluster}'
    )
    return_code = inspector_run_workload_list_helper(
        args, command_description, inspector_file
    )
    if return_code != 0:
      final_return_code = return_code
      xpk_print(
          f'inspector failed in description: {command_description} return code:'
          f' {return_code}'
      )

  # If a workload argument is provided, list out workload specific details.
  if args.workload:
    xpk_print(args.workload)
    args.filter_by_job = args.workload
    args.filter_by_status = 'EVERYTHING'
    command_description = (
        f'xpk workload list --filter-by-status={args.filter_by_status}'
        f' --filter-by-job={args.filter_by_job} --project={args.project} --zone={args.zone}'
        f' --cluster={args.cluster}'
    )
    return_code = inspector_run_workload_list_helper(
        args, command_description, inspector_file
    )
    if return_code != 0:
      final_return_code = return_code
      xpk_print(
          f'inspector failed in description: {command_description} return code:'
          f' {return_code}'
      )

    command = f'kubectl describe jobsets {args.workload}'
    command_description = f'Jobset config for {args.workload}'
    return_code = inspector_run_command_helper(
        args, command, command_description, inspector_file
    )
    if return_code != 0:
      final_return_code = return_code
      xpk_print(
          f'inspector failed in command: {command} description:'
          f' {command_description} return code: {return_code}'
      )

    command = f'kubectl describe workloads jobset-{args.workload}'
    command_description = f'Workload config for {args.workload}'
    return_code = inspector_run_command_helper(
        args, command, command_description, inspector_file
    )
    if return_code != 0:
      final_return_code = return_code
      xpk_print(
          f'inspector failed in command: {command} description:'
          f' {command_description} return code: {return_code}'
      )

  # Cloud Console Links:
  workload_links = []
  if args.workload:
    workload_links = [(
        f'Cloud Console for the workload {args.workload}',
        # pylint: disable=line-too-long
        f'https://console.cloud.google.com/kubernetes/service/{zone_to_region(args.zone)}/{args.cluster}/default/{args.workload}/details?project={args.project}',
    )]

  links = [
      (
          'Cloud Console for the GKE Cluster',
          # pylint: disable=line-too-long
          f'https://console.cloud.google.com/kubernetes/clusters/details/{zone_to_region(args.zone)}/{args.cluster}/details?project={args.project}',
      ),
      (
          'Cloud Console for all workloads in GKE Cluster',
          # pylint: disable=line-too-long
          f'https://console.cloud.google.com/kubernetes/workload/overview?project={args.project}&pageState=((gke%2F{zone_to_region(args.zone)}%2F{args.cluster}))',
      ),
      (
          'Cloud Console for IAM Permissions',
          f'https://console.cloud.google.com/iam-admin/iam?project={args.project}',
      ),
      (
          'Cloud Console for Quotas',
          f'https://console.cloud.google.com/iam-admin/quotas?project={args.project}',
      ),
  ]
  links.extend(workload_links)

  for description, workload_link in links:
    return_code = inspector_output_link_helper(
        args, workload_link, description, inspector_file
    )
    if return_code != 0:
      final_return_code = return_code
      xpk_print(
          f'inspector failed in link: {workload_link} description:'
          f' {description} return code: {return_code}'
      )

  # Summarize inspector:
  xpk_print(f'Find xpk inspector output file: {inspector_file.name}')

  if final_return_code != 0:
    xpk_print(
        'Something was unable to run in xpk inspector, please look through the'
        ' output as it may clue to the failure reason. Return Code:'
        f' {final_return_code}'
    )
  xpk_exit(final_return_code)
