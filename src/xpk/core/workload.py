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

import yaml

from ..utils import templates
from ..utils.console import xpk_exit, xpk_print
from .capacity import H100_DEVICE_TYPE, H100_MEGA_DEVICE_TYPE
from .commands import run_command_for_value
from .gcloud_context import zone_to_region
from .storage import Storage, get_storage_volume_mounts_for_gpu
from .system_characteristics import SystemCharacteristics

RXDM_CONTAINER_A3HIGH_PATH = '/../templates/rxdm_container_a3high.yaml'
RXDM_CONTAINER_A3MEGA_PATH = '/../templates/rxdm_container_a3mega.yaml'


def workload_list_awk_command(filter_key) -> str:
  """Function returns the awk command needed from the filter specified.

  Args:
    filter_key: workload list filter to awk against

  Returns:
    awk command to use in filtering workload list.
  """

  return f" | awk -e 'NR == 1 || {filter_key} {{print $0}}'"


def determine_workload_list_filter_by_status(args) -> str:
  """Function to create the filtered view of workload list.

  Args:
    args: user provided arguments for running the command.

  Returns:
    the argument needed to filter by status of jobs in workload list.
  """

  # Argument positions related to columns created by workload list command.
  status_arg = '$7'
  running_vms_arg = '$5'
  status_verbose_arg = '$9'
  if args.filter_by_status == 'EVERYTHING':
    return ''
  elif args.filter_by_status == 'RUNNING':
    # Running includes the status Admitted or Evicted, and when the number of
    # vms running is > 0.
    return workload_list_awk_command(
        f'({status_arg} ~ "Admitted|Evicted" && {running_vms_arg} ~ /^[0-9]+$/'
        f' && {running_vms_arg} > 0)'
    )
  elif args.filter_by_status == 'QUEUED':
    # Queued includes the status Admitted or Evicted, and when the number of
    # vms running is 0.
    return workload_list_awk_command(
        f'({status_arg} ~ "Admitted|Evicted|QuotaReserved" &&'
        f' ({running_vms_arg} ~ "<none>" || {running_vms_arg} == 0))'
    )
  elif args.filter_by_status == 'FINISHED':
    return workload_list_awk_command(f'{status_arg} == "Finished"')
  elif args.filter_by_status == 'FAILED':
    # Failed includes the status Finished, and when the verbose reason is failed.
    return workload_list_awk_command(
        f'({status_arg} == "Finished" && {status_verbose_arg} ~ "failed")'
    )
  elif args.filter_by_status == 'SUCCESSFUL':
    # Failed includes the status Finished, and when the verbose reason is finished/success.
    return workload_list_awk_command(
        f'({status_arg} == "Finished" && {status_verbose_arg} ~ "finished")'
    )
  raise RuntimeError(f'Can not find filter type: {args.filter_by_status}')


def determine_workload_list_filter_by_job(args) -> str:
  """Function to filter view of workload list based on job name.

  Args:
    args: user provided arguments for running the command.

  Returns:
    the argument needed to filter job names from workload list
  """
  # Argument positions related to columns created by workload list command.
  if not hasattr(args, 'filter_by_job') or args.filter_by_job is None:
    return ''
  else:
    job_name_arg = '$1'
    return workload_list_awk_command(f'{job_name_arg} ~ "{args.filter_by_job}"')


def get_workload_list(args) -> tuple[int, str]:
  """Function to get the list of the workloads in the cluster.

  Args:
    args: user provided arguments for running the command.

  Returns:
    return_code: 0 if successful and 1 otherwise.
    return_value: workloads in the cluster matching the criteria.
  """
  columns = {
      'Jobset Name': '.metadata.ownerReferences[0].name',
      'Created Time': '.metadata.creationTimestamp',
      'Priority': '.spec.priorityClassName',
      'TPU VMs Needed': '.spec.podSets[0].count',
      'TPU VMs Running/Ran': '.status.admission.podSetAssignments[-1].count',
      'TPU VMs Done': '.status.reclaimablePods[0].count',
      'Status': '.status.conditions[-1].type',
      'Status Message': '.status.conditions[-1].message',
      'Status Time': '.status.conditions[-1].lastTransitionTime',
  }
  s = ','.join([key + ':' + value for key, value in columns.items()])

  workload_list_filter_status_cmd = determine_workload_list_filter_by_status(
      args
  )
  workload_list_filter_job_cmd = determine_workload_list_filter_by_job(args)
  command = (
      f'kubectl get workloads -o=custom-columns="{s}" '
      f'{workload_list_filter_status_cmd} {workload_list_filter_job_cmd}'
  )

  task = f'List Jobs with filter-by-status={args.filter_by_status}'
  if hasattr(args, 'filter_by_job'):
    task += f' with filter-by-job={args.filter_by_job}'

  return_code, return_value = run_command_for_value(command, task, args)
  return return_code, return_value


def check_if_workload_exists(args) -> bool:
  """Check if workload exists.

  Args:
     args: user provided arguments for running the command.

  Returns:
    returns true if workload exist, otherwise returns false.
  """
  columns = {
      'Jobset': '.metadata.ownerReferences[0].name',
  }

  s = ','.join([key + ':' + value for key, value in columns.items()])

  command = f"kubectl get workloads -o=custom-columns='{s}'"
  return_code, return_msg = run_command_for_value(
      command, 'Check if Workload Already Exists', args
  )

  if return_code != 0:
    xpk_print(f'List Job request returned ERROR {return_code}')
    xpk_exit(return_code)

  lines = return_msg.split('\n')
  new_workload_name = args.workload
  for line in lines:
    if line == new_workload_name:
      return True
  return False


def wait_for_job_completion(args) -> int:
  """Function to wait for job completion.

  Args:
    args: user provided arguments for running the command.

  Returns:
    return_code: 0 if successful, 124 if timeout, 125 if unsuccessful job, 1 otherwise
  """
  # Check that the workload exists
  args.workload = args.wait_for_job_completion
  workload_exists = check_if_workload_exists(args)
  if not workload_exists:
    xpk_print(f'Workload named {args.workload} does not exist.')
    return 1

  # Get the full workload name
  get_workload_name_cmd = f'kubectl get workloads | grep jobset-{args.workload}'
  return_code, return_value = run_command_for_value(
      get_workload_name_cmd, 'Get full workload name', args
  )
  if return_code != 0:
    xpk_print(f'Get full workload name request returned ERROR {return_code}')
    return return_code
  full_workload_name = return_value.split(' ')[0]

  # Call kubectl wait on the workload using the full workload name
  timeout_val = args.timeout if args.timeout is not None else -1
  timeout_msg = (
      f'{timeout_val}s' if timeout_val != -1 else 'max timeout (1 week)'
  )
  wait_cmd = (
      "kubectl  wait --for jsonpath='.status.conditions[-1].type'=Finished"
      f' workload {full_workload_name} --timeout={timeout_val}s'
  )
  return_code, return_value = run_command_for_value(
      wait_cmd,
      f'Wait for workload to finish with timeout of {timeout_msg}',
      args,
      print_timer=True,
  )
  if return_code != 0:
    if 'timed out' in return_value:
      xpk_print(
          f'Timed out waiting for your workload after {timeout_msg}, see your'
          ' workload here:'
          # pylint: disable=line-too-long
          f' https://console.cloud.google.com/kubernetes/service/{zone_to_region(args.zone)}/{args.cluster}/default/{args.workload}/details?project={args.project}'
      )
      return 124
    else:
      xpk_print(f'{return_value}')
      xpk_print(f'Wait for workload returned ERROR {return_code}')
      return return_code
  xpk_print(
      'Finished waiting for your workload, see your workload here:'
      # pylint: disable=line-too-long
      f' https://console.cloud.google.com/kubernetes/service/{zone_to_region(args.zone)}/{args.cluster}/default/{args.workload}/details?project={args.project}'
  )
  status_cmd = (
      f'kubectl get jobset {args.workload} -o'
      " jsonpath='{.status.conditions[-1].type}'"
  )
  return_code, return_value = run_command_for_value(
      status_cmd, 'Get jobset status', args
  )
  if return_code != 0:
    xpk_print(f'Get workload status request returned ERROR {return_code}')
    return return_code
  xpk_print(f'Your workload finished with status: {return_value}')
  if return_value != 'Completed':
    xpk_print('Your workload did not complete successfully')
    return 125
  return 0


def add_gpu_rxdm_container(
    jobset_manifest_str: str,
    system: SystemCharacteristics,
    all_storages: list[Storage],
) -> str:
  """Add gpu rxdm container to jobset manifest based on user provided arguments.

  Args:
    jobset_manifest_str: the JobSet manifest as a YAML string.
    system: system characteristics.
    all_storages: list of all storages.

  Returns:
    str: the modified JobSet manifest as a YAML string.
  """
  if system.device_type == H100_DEVICE_TYPE:
    gpu_rxdm_container = templates.load(RXDM_CONTAINER_A3HIGH_PATH)
  elif system.device_type == H100_MEGA_DEVICE_TYPE:
    gpu_rxdm_container = templates.load(RXDM_CONTAINER_A3MEGA_PATH)
  else:
    return jobset_manifest_str

  storage_volume_mounts = get_storage_volume_mounts_for_gpu(all_storages)
  gpu_rxdm_container['volumeMounts'].extend(storage_volume_mounts)

  manifest = yaml.safe_load(jobset_manifest_str)

  for job in manifest['spec']['replicatedJobs']:
    job['template']['spec']['template']['spec']['containers'].append(
        gpu_rxdm_container
    )

  return yaml.dump(manifest, sort_keys=False)
