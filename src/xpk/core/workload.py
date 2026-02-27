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

from dataclasses import dataclass
from enum import Enum, auto
import re
from typing import Callable, Optional

from ..utils.console import xpk_exit, xpk_print
from .commands import run_command_for_value
from .gcloud_context import get_cluster_location

_WORKLOAD_LIST_DELIMITER = '~'


def _safe_int(s: str) -> int:
  try:
    return int(s)
  except ValueError:
    return 0


@dataclass
class _WorkloadListColumn:
  header: str
  jsonpath: str
  formatter: Callable[[str], str] = lambda x: x


def _sum_counts(value: str) -> str:
  """Sums space-separated numbers in a string. Returns <none> if empty."""
  if not value or not value.strip():
    return '<none>'
  try:
    total = sum(int(x) for x in value.split())
    return str(total)
  except ValueError:
    return '<none>'


class _WorkloadListColumnType(Enum):
  JOBSET_NAME = auto()
  CREATED_TIME = auto()
  PRIORITY = auto()
  TPU_VMS_NEEDED = auto()
  TPU_VMS_RUNNING_RAN = auto()
  TPU_VMS_DONE = auto()
  STATUS = auto()
  STATUS_MESSAGE = auto()
  STATUS_TIME = auto()


_WORKLOAD_LIST_COLUMN_MAP: dict[
    _WorkloadListColumnType, _WorkloadListColumn
] = {
    _WorkloadListColumnType.JOBSET_NAME: _WorkloadListColumn(
        'Jobset Name', '{.metadata.ownerReferences[0].name}'
    ),
    _WorkloadListColumnType.CREATED_TIME: _WorkloadListColumn(
        'Created Time', '{.metadata.creationTimestamp}'
    ),
    _WorkloadListColumnType.PRIORITY: _WorkloadListColumn(
        'Priority', '{.spec.podSets[0].template.spec.priorityClassName}'
    ),
    _WorkloadListColumnType.TPU_VMS_NEEDED: _WorkloadListColumn(
        'TPU VMs Needed', '{.spec.podSets[*].count}', _sum_counts
    ),
    _WorkloadListColumnType.TPU_VMS_RUNNING_RAN: _WorkloadListColumn(
        'TPU VMs Running/Ran',
        '{.status.admission.podSetAssignments[*].count}',
        _sum_counts,
    ),
    _WorkloadListColumnType.TPU_VMS_DONE: _WorkloadListColumn(
        'TPU VMs Done', '{.status.reclaimablePods[*].count}', _sum_counts
    ),
    _WorkloadListColumnType.STATUS: _WorkloadListColumn(
        'Status', '{.status.conditions[-1].type}'
    ),
    _WorkloadListColumnType.STATUS_MESSAGE: _WorkloadListColumn(
        'Status Message', '{.status.conditions[-1].message}'
    ),
    _WorkloadListColumnType.STATUS_TIME: _WorkloadListColumn(
        'Status Time', '{.status.conditions[-1].lastTransitionTime}'
    ),
}

_WORKLOAD_LIST_DISPLAY_ORDER = [
    _WorkloadListColumnType.JOBSET_NAME,
    _WorkloadListColumnType.CREATED_TIME,
    _WorkloadListColumnType.PRIORITY,
    _WorkloadListColumnType.TPU_VMS_NEEDED,
    _WorkloadListColumnType.TPU_VMS_RUNNING_RAN,
    _WorkloadListColumnType.TPU_VMS_DONE,
    _WorkloadListColumnType.STATUS,
    _WorkloadListColumnType.STATUS_MESSAGE,
    _WorkloadListColumnType.STATUS_TIME,
]
_HEADERS = [
    _WORKLOAD_LIST_COLUMN_MAP[col].header
    for col in _WORKLOAD_LIST_DISPLAY_ORDER
]


def _fetch_workloads(
    filter_by_status: str,
    filter_by_job: Optional[str] = None,
) -> tuple[int, list[dict[_WorkloadListColumnType, str]]]:
  """Fetches and parses the raw workload list from the cluster."""
  row_path = _WORKLOAD_LIST_DELIMITER.join([
      f'{col.name}={_WORKLOAD_LIST_COLUMN_MAP[col].jsonpath}'
      for col in _WORKLOAD_LIST_DISPLAY_ORDER
  ])
  jsonpath_str = f'{{range .items[*]}}{row_path}{{"\n"}}{{end}}'

  command = (
      f"kubectl get workloads --ignore-not-found -o=jsonpath='{jsonpath_str}'"
  )

  task = f'List Jobs with filter-by-status={filter_by_status}'
  if filter_by_job:
    task += f' with filter-by-job={filter_by_job}'

  return_code, data = run_command_for_value(
      command, task, dry_run_return_val=''
  )

  if return_code != 0:
    return return_code, []

  data_rows = []
  if data:
    for line in data.splitlines():
      row_dict = {}
      for kv in line.split(_WORKLOAD_LIST_DELIMITER):
        if '=' in kv:
          key_str, val = kv.split('=', 1)
          try:
            col_enum = _WorkloadListColumnType[key_str]
            row_dict[col_enum] = val
          except KeyError:
            xpk_print(f'Warning: Unrecognized column key: {key_str}')
      if row_dict:
        data_rows.append(row_dict)

  return 0, data_rows


def _format_columns(
    rows: list[dict[_WorkloadListColumnType, str]],
) -> list[dict[_WorkloadListColumnType, str]]:
  """Applies formatters to all columns in the raw rows."""
  formatted_rows = []
  for row_dict in rows:
    row_data = {}
    for col_enum in _WORKLOAD_LIST_DISPLAY_ORDER:
      col_metadata = _WORKLOAD_LIST_COLUMN_MAP[col_enum]
      row_data[col_enum] = col_metadata.formatter(row_dict.get(col_enum, ''))
    formatted_rows.append(row_data)
  return formatted_rows


def _filter_workload(
    row_data: dict[_WorkloadListColumnType, str],
    filter_by_status: str,
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
  if (
      filter_by_job
      and filter_by_job not in row_data[_WorkloadListColumnType.JOBSET_NAME]
  ):
    return False

  status = row_data[_WorkloadListColumnType.STATUS]
  message = row_data[_WorkloadListColumnType.STATUS_MESSAGE]
  running_str = row_data[_WorkloadListColumnType.TPU_VMS_RUNNING_RAN]

  match filter_by_status:
    case 'EVERYTHING':
      return True
    case 'RUNNING':
      return (
          status in ['Admitted', 'Evicted']
          and running_str != '<none>'
          and _safe_int(running_str) > 0
      )
    case 'QUEUED':
      return status in ['Admitted', 'Evicted', 'QuotaReserved'] and (
          running_str == '<none>' or _safe_int(running_str) == 0
      )
    case 'FINISHED':
      return status == 'Finished'
    case 'FAILED':
      return status == 'Finished' and 'failed' in message
    case 'SUCCESSFUL':
      return status == 'Finished' and 'finished' in message
    case _:
      raise RuntimeError(f'Can not find filter type: {filter_by_status}')


def _filter_workloads(
    rows: list[dict[_WorkloadListColumnType, str]],
    filter_by_status: str,
    filter_by_job: Optional[str],
) -> list[dict[_WorkloadListColumnType, str]]:
  """Filters rows based on status and job filters."""
  return [
      row
      for row in rows
      if _filter_workload(row, filter_by_status, filter_by_job)
  ]


def _render_workloads(
    rows: list[dict[_WorkloadListColumnType, str]],
) -> str:
  """Formats the filtered rows into a string table."""
  if not rows:
    return ''

  filtered_rows = []
  for row_data in rows:
    row_list = [row_data[col_enum] for col_enum in _WORKLOAD_LIST_DISPLAY_ORDER]
    filtered_rows.append(row_list)

  col_widths = [len(h) for h in _HEADERS]
  for row in filtered_rows:
    for i, val in enumerate(row):
      col_widths[i] = max(col_widths[i], len(val))

  fmt = '   '.join(f'{{:<{w}}}' for w in col_widths)

  output = [fmt.format(*_HEADERS)]
  for row in filtered_rows:
    output.append(fmt.format(*row))

  return '\n'.join(output)


def get_workload_list(args) -> tuple[int, str]:
  """Function to get the list of the workloads in the cluster.

  Args:
    args: user provided arguments for running the command.

  Returns:
    return_code: 0 if successful and 1 otherwise.
    return_value: workloads in the cluster matching the criteria.
  """
  filter_by_job = getattr(args, 'filter_by_job', None)
  return_code, raw_rows = _fetch_workloads(args.filter_by_status, filter_by_job)
  if return_code != 0:
    return return_code, ''

  formatted_rows = _format_columns(raw_rows)

  filtered_rows = _filter_workloads(
      formatted_rows, args.filter_by_status, filter_by_job
  )

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
