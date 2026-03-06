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
from dataclasses import dataclass
from enum import Enum
import re
from typing import Any, Optional, Callable, Union

from ..utils.console import xpk_exit, xpk_print
from .commands import run_command_for_value
from .gcloud_context import get_cluster_location


def _safe_int(val: Any) -> int:
  try:
    return int(val)
  except (ValueError, TypeError):
    return 0


class _WorkloadStatus(Enum):
  ADMITTED = 'Admitted'
  EVICTED = 'Evicted'
  QUOTA_RESERVED = 'QuotaReserved'
  FINISHED = 'Finished'
  UNKNOWN = 'Unknown'


class _StatusFilter(Enum):
  EVERYTHING = 'EVERYTHING'
  RUNNING = 'RUNNING'
  QUEUED = 'QUEUED'
  FINISHED = 'FINISHED'
  FAILED = 'FAILED'
  SUCCESSFUL = 'SUCCESSFUL'


@dataclass
class _WorkloadListRow:
  """A row in the workload list table."""

  jobset_name: Optional[str]
  created_time: Optional[str]
  priority: Optional[str]
  tpu_vms_needed: Optional[int]
  tpu_vms_running_ran: Optional[int]
  tpu_vms_done: Optional[int]
  status: Optional[_WorkloadStatus]
  status_message: Optional[str]
  status_time: Optional[str]


@dataclass
class _WorkloadListColumn:
  header: str
  getter: Callable[
      [_WorkloadListRow], Optional[Union[str, int, _WorkloadStatus]]
  ]


_WORKLOAD_COLUMNS: list[_WorkloadListColumn] = [
    _WorkloadListColumn('Jobset Name', lambda row: row.jobset_name),
    _WorkloadListColumn('Created Time', lambda row: row.created_time),
    _WorkloadListColumn('Priority', lambda row: row.priority),
    _WorkloadListColumn('TPU VMs Needed', lambda row: row.tpu_vms_needed),
    _WorkloadListColumn(
        'TPU VMs Running/Ran', lambda row: row.tpu_vms_running_ran
    ),
    _WorkloadListColumn('TPU VMs Done', lambda row: row.tpu_vms_done),
    _WorkloadListColumn('Status', lambda row: row.status),
    _WorkloadListColumn('Status Message', lambda row: row.status_message),
    _WorkloadListColumn('Status Time', lambda row: row.status_time),
]


def _parse_workload_status(
    status_str: Optional[str],
) -> Optional[_WorkloadStatus]:
  if not status_str:
    return None
  try:
    return _WorkloadStatus(status_str)
  except ValueError:
    return _WorkloadStatus.UNKNOWN


def _parse_workload_item(item: dict[str, Any]) -> _WorkloadListRow:
  owner_refs = item.get('metadata', {}).get('ownerReferences') or [{}]
  jobset_name = owner_refs[0].get('name', '') or None

  created_time = item.get('metadata', {}).get('creationTimestamp', '') or None
  priority = item.get('spec', {}).get('priorityClassName', '') or None

  pod_sets = item.get('spec', {}).get('podSets') or []
  tpu_vms_needed = (
      sum(_safe_int(ps.get('count')) for ps in pod_sets) if pod_sets else None
  )

  pod_set_assignments = (
      item.get('status', {}).get('admission', {}).get('podSetAssignments') or []
  )
  tpu_vms_running_ran = (
      sum(_safe_int(psa.get('count')) for psa in pod_set_assignments)
      if pod_set_assignments
      else None
  )

  reclaimable_pods = item.get('status', {}).get('reclaimablePods') or []
  tpu_vms_done = (
      sum(_safe_int(rp.get('count')) for rp in reclaimable_pods)
      if reclaimable_pods
      else None
  )

  conditions = item.get('status', {}).get('conditions') or [{}]
  status_str = conditions[-1].get('type', '')
  status = _parse_workload_status(status_str)

  status_message = conditions[-1].get('message', '') or None
  status_time = conditions[-1].get('lastTransitionTime', '') or None

  return _WorkloadListRow(
      jobset_name=jobset_name,
      created_time=created_time,
      priority=priority,
      tpu_vms_needed=tpu_vms_needed,
      tpu_vms_running_ran=tpu_vms_running_ran,
      tpu_vms_done=tpu_vms_done,
      status=status,
      status_message=status_message,
      status_time=status_time,
  )


def _fetch_workloads(
    filter_by_status: _StatusFilter,
    filter_by_job: Optional[str] = None,
) -> tuple[int, list[_WorkloadListRow]]:
  """Fetches and parses the raw workload list from the cluster."""
  command = 'kubectl get workloads --ignore-not-found -o=json'

  task = f'List Jobs with filter-by-status={filter_by_status.value}'
  if filter_by_job:
    task += f' with filter-by-job={filter_by_job}'

  return_code, data = run_command_for_value(
      command, task, dry_run_return_val=''
  )

  if return_code != 0:
    return return_code, []

  if not data:
    return 0, []

  try:
    parsed_data = json.loads(data)
  except json.JSONDecodeError:
    xpk_print('Error: Failed to parse JSON output from kubectl.')
    return 1, []

  data_rows = []
  for item in parsed_data.get('items', []):
    data_rows.append(_parse_workload_item(item))

  return 0, data_rows


def _filter_workload(
    row_data: _WorkloadListRow,
    filter_by_status: _StatusFilter,
    filter_by_job: Optional[str],
) -> bool:
  """Filters a workload based on status and job name.

  Args:
    row_data: The parsed row data keyed by column type.
    filter_by_status: The status filter to apply.
    filter_by_job: The job name filter to apply.

  Returns:
    True if the workload should be included, False otherwise.
  """
  if filter_by_job and filter_by_job not in (row_data.jobset_name or ''):
    return False

  status = row_data.status
  message = row_data.status_message or ''
  running_count = row_data.tpu_vms_running_ran or 0

  match filter_by_status:
    case _StatusFilter.EVERYTHING:
      return True
    case _StatusFilter.RUNNING:
      return (
          status in [_WorkloadStatus.ADMITTED, _WorkloadStatus.EVICTED]
          and running_count > 0
      )
    case _StatusFilter.QUEUED:
      return (
          status
          in [
              _WorkloadStatus.ADMITTED,
              _WorkloadStatus.EVICTED,
              _WorkloadStatus.QUOTA_RESERVED,
          ]
          and running_count == 0
      )
    case _StatusFilter.FINISHED:
      return status == _WorkloadStatus.FINISHED
    case _StatusFilter.FAILED:
      return status == _WorkloadStatus.FINISHED and 'failed' in message.lower()
    case _StatusFilter.SUCCESSFUL:
      return (
          status == _WorkloadStatus.FINISHED and 'finished' in message.lower()
      )
    case _:
      raise RuntimeError(f'Can not find filter type: {filter_by_status}')


def _filter_workloads(
    rows: list[_WorkloadListRow],
    filter_by_status: _StatusFilter,
    filter_by_job: Optional[str],
) -> list[_WorkloadListRow]:
  """Filters rows based on status and job filters."""
  return [
      row
      for row in rows
      if _filter_workload(row, filter_by_status, filter_by_job)
  ]


def _render_workloads(
    rows: list[_WorkloadListRow],
) -> str:
  """Formats the filtered rows into a string table."""
  headers = [col.header for col in _WORKLOAD_COLUMNS]

  def format_val(val) -> str:
    if val is None:
      return '<none>'
    if isinstance(val, Enum):
      return str(val.value)
    return str(val)

  filtered_rows = []
  for row_data in rows:
    filtered_rows.append(
        [format_val(col.getter(row_data)) for col in _WORKLOAD_COLUMNS]
    )

  col_widths = [len(h) for h in headers]
  for row in filtered_rows:
    for i, val in enumerate(row):
      col_widths[i] = max(col_widths[i], len(val))

  fmt = '   '.join(f'{{:<{w}}}' for w in col_widths)

  output = [fmt.format(*headers)]
  for row in filtered_rows:
    output.append(fmt.format(*row))

  return '\n'.join(output)


def _get_status_filter(filter_by_status: str) -> _StatusFilter:
  try:
    return _StatusFilter(filter_by_status.upper())
  except ValueError:
    xpk_print(
        f'Warning: Unrecognized status filter {filter_by_status},'
        ' defaulting to EVERYTHING.'
    )
    return _StatusFilter.EVERYTHING


def get_workload_list(args) -> tuple[int, str]:
  """Function to get the list of the workloads in the cluster.

  Args:
    args: user provided arguments for running the command.

  Returns:
    return_code: 0 if successful and 1 otherwise.
    return_value: workloads in the cluster matching the criteria.
  """
  filter_by_job = getattr(args, 'filter_by_job', None)
  filter_by_status = _get_status_filter(args.filter_by_status)

  return_code, raw_rows = _fetch_workloads(filter_by_status, filter_by_job)
  if return_code != 0:
    return return_code, ''

  filtered_rows = _filter_workloads(raw_rows, filter_by_status, filter_by_job)

  formatted_output = _render_workloads(filtered_rows)

  return 0, formatted_output


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
      "kubectl  wait --for jsonpath='.status.conditions[-1].type'=Finished"
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
      " jsonpath='{.status.conditions[-1].type}'"
  )
  return_code, return_value = run_command_for_value(
      status_cmd, 'Get jobset status'
  )
  if return_code != 0:
    xpk_print(f'Get workload status request returned ERROR {return_code}')
    return return_code
  xpk_print(f'Your workload finished with status: {return_value}')
  if return_value != 'Completed':
    xpk_print('Your workload did not complete successfully')
    return 125
  return 0


_GCP_NAME_FILTER_VALUE_REGEX = re.compile(r'[a-z0-9\-]+')
"""Defines correct name prefix value (contains only letters, numbers and dashes) that can be used in GCP filter chips."""


def get_jobsets_list_gcp_link(project: str) -> str:
  """Returns a link to Cloud Console JobSets list"""

  return f'https://console.cloud.google.com/kubernetes/aiml/deployments/jobs?project={project}'
