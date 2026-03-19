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

import json
import re
from ..utils.console import xpk_exit, xpk_print
from .commands import run_command_for_value
from .gcloud_context import get_cluster_location


def get_workload_list(args) -> tuple[int, str]:
  """Function to get the list of the workloads in the cluster.

  Args:
    args: user provided arguments for running the command.

  Returns:
    return_code: 0 if successful and 1 otherwise.
    return_value: workloads in the cluster matching the criteria.
  """
  command = 'kubectl get workloads --ignore-not-found -o json'

  task = f'List Jobs with filter-by-status={args.filter_by_status}'
  if hasattr(args, 'filter_by_job') and args.filter_by_job:
    task += f' with filter-by-job={args.filter_by_job}'

  return_code, return_value = run_command_for_value(command, task)
  if return_code != 0:
    return return_code, return_value

  try:
    if not return_value.strip():
      workloads_json = {'items': []}
    else:
      workloads_json = json.loads(return_value)
  except json.JSONDecodeError:
    return 1, f"Failed to parse kubectl output as JSON: {return_value}"

  items = workloads_json.get('items', [])
  
  rows = []
  headers = [
      'Jobset Name',
      'Created Time',
      'Priority',
      'TPU VMs Needed',
      'TPU VMs Running/Ran',
      'TPU VMs Done',
      'Status',
      'Status Message',
      'Status Time',
  ]
  
  for item in items:
    metadata = item.get('metadata', {})
    spec = item.get('spec', {})
    status = item.get('status', {})
    
    owner_refs = metadata.get('ownerReferences', [])
    jobset_name = owner_refs[0].get('name', '<none>') if owner_refs else '<none>'
    
    if hasattr(args, 'filter_by_job') and args.filter_by_job:
      if not re.search(args.filter_by_job, jobset_name):
        continue
        
    created_time = metadata.get('creationTimestamp', '<none>')
    priority = spec.get('priorityClassName', '<none>')
    
    pod_sets = spec.get('podSets', [])
    tpu_vms_needed = str(pod_sets[0].get('count', '<none>')) if pod_sets else '<none>'
    
    admission = status.get('admission', {})
    pod_set_assignments = admission.get('podSetAssignments', [])
    tpu_vms_running = str(pod_set_assignments[-1].get('count', '<none>')) if pod_set_assignments else '<none>'
    
    reclaimable = status.get('reclaimablePods', [])
    tpu_vms_done = str(reclaimable[0].get('count', '<none>')) if reclaimable else '<none>'
    
    conditions = status.get('conditions', [])
    if conditions:
      latest_cond = sorted(conditions, key=lambda c: c.get('lastTransitionTime', ''))[-1]
      cond_type = latest_cond.get('type', '<none>')
      cond_msg = latest_cond.get('message', '<none>')
      cond_time = latest_cond.get('lastTransitionTime', '<none>')
    else:
      cond_type = '<none>'
      cond_msg = '<none>'
      cond_time = '<none>'
      
    keep = False
    filter_status = getattr(args, 'filter_by_status', 'EVERYTHING')
    if filter_status == 'EVERYTHING':
      keep = True
    elif filter_status == 'RUNNING':
      if cond_type in ('Admitted', 'Evicted') and tpu_vms_running.isdigit() and int(tpu_vms_running) > 0:
        keep = True
    elif filter_status == 'QUEUED':
      if cond_type in ('Admitted', 'Evicted', 'QuotaReserved') and (tpu_vms_running == '<none>' or tpu_vms_running == '0'):
        keep = True
    elif filter_status == 'FINISHED':
      if cond_type == 'Finished':
        keep = True
    elif filter_status == 'FAILED':
      if cond_type == 'Finished' and 'failed' in cond_msg.lower():
        keep = True
    elif filter_status == 'SUCCESSFUL':
      if cond_type == 'Finished' and ('finished' in cond_msg.lower() or 'success' in cond_msg.lower()):
        keep = True
    else:
      return 1, f"Can not find filter type: {filter_status}"
        
    if keep:
      rows.append([jobset_name, created_time, priority, tpu_vms_needed, tpu_vms_running, tpu_vms_done, cond_type, cond_msg, cond_time])
      
  all_data = [headers] + rows
  col_widths = [max(len(str(item)) for item in col) for col in zip(*all_data)]
  
  lines = []
  for row in all_data:
      lines.append('   '.join(str(item).ljust(width) for item, width in zip(row, col_widths)))
      
  return 0, '\n'.join(lines)


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
      command, 'Check if Workload Already Exists'
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
      get_workload_name_cmd, 'Get full workload name'
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
      'kubectl wait --for=condition=Finished'
      f' workload {full_workload_name} --timeout={timeout_val}s'
  )
  return_code, return_value = run_command_for_value(
      wait_cmd,
      f'Wait for workload to finish with timeout of {timeout_msg}',
      print_timer=True,
  )
  if return_code != 0:
    if 'timed out' in return_value:
      xpk_print(
          f'Timed out waiting for your workload after {timeout_msg}, see your'
          ' workload here:'
          # pylint: disable=line-too-long
          f' https://console.cloud.google.com/kubernetes/service/{get_cluster_location(args.project, args.cluster, args.zone)}/{args.cluster}/default/{args.workload}/details?project={args.project}'
      )
      return 124
    else:
      xpk_print(f'{return_value}')
      xpk_print(f'Wait for workload returned ERROR {return_code}')
      return return_code
  xpk_print(
      'Finished waiting for your workload, see your workload here:'
      # pylint: disable=line-too-long
      f' https://console.cloud.google.com/kubernetes/service/{get_cluster_location(args.project, args.cluster, args.zone)}/{args.cluster}/default/{args.workload}/details?project={args.project}'
  )
  status_cmd = (
      f'kubectl get jobset {args.workload} -o'
      " jsonpath='{.status.conditions[?(@.type==\"Completed\")].status}'"
  )
  return_code, return_value = run_command_for_value(
      status_cmd, 'Get jobset status'
  )
  if return_code != 0:
    xpk_print(f'Get workload status request returned ERROR {return_code}')
    return return_code

  if return_value == 'True':
    xpk_print(f'Your workload finished with Completed status: {return_value}')
    return 0

  # If not True, check for Failed condition to output a cleaner message
  failed_status_cmd = (
      f'kubectl get jobset {args.workload} -o'
      " jsonpath='{.status.conditions[?(@.type==\"Failed\")].status}'"
  )
  failed_return_code, failed_return_value = run_command_for_value(
      failed_status_cmd, 'Get jobset failed status'
  )
  if failed_return_code != 0:
    xpk_print(f'Get workload failed status request returned ERROR {failed_return_code}')
    return failed_return_code
    
  if failed_return_value == 'True':
    xpk_print(f'Your workload failed with Failed status: {failed_return_value}')
  else:
    xpk_print('Your workload finished without a Completed or Failed status')
    
  xpk_print('Your workload did not complete successfully')
  return 125


GCP_NAME_FILTER_VALUE_REGEX = re.compile(r'[a-z0-9\-]+')
"""Defines correct name prefix value (contains only letters, numbers and dashes) that can be used in GCP filter chips."""


def get_jobsets_list_gcp_link(project: str) -> str:
  """Returns a link to Cloud Console JobSets list"""

  return f'https://console.cloud.google.com/kubernetes/aiml/deployments/jobs?project={project}'
