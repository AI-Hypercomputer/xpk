"""
Copyright 2025 Google LLC

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

from ..utils.console import xpk_print
from .commands import run_command_for_value


def get_gke_dashboard(args, dashboard_filter) -> tuple[bool, str | None]:
  """Get the identifier of GKE dashboard deployed in the project.

  Args:
    args: user provided arguments for running the command.

  Returns:
    bool:
      True if 'gcloud monitoring dashboards list' returned an error or
      multiple dashboards with same filter exist in the project,
      False otherwise.
    str:
      identifier of dashboard if deployed in project,
      None otherwise.
  """
  command = (
      'gcloud monitoring dashboards list'
      f' --project={args.project} --filter="{dashboard_filter}"'
      ' --format="value(name)" --verbosity=error'
  )

  return_code, return_value = run_command_for_value(
      command, 'GKE Dashboard List', args
  )

  if return_code != 0:
    xpk_print(
        f'GKE Dashboard List request returned ERROR {return_code}. If there is'
        ' a permissions error, please check'
        ' https://github.com/google/xpk/blob/main/README.md#roles-needed-based-on-permission-errors'
        ' for possible solutions.'
    )
    return True, None

  if not return_value:
    xpk_print(
        f'No dashboard with {dashboard_filter} found in the'
        f' project:{args.project}.'
    )
    return False, return_value

  dashboards = return_value.strip().split('\n')
  if len(dashboards) > 1:
    xpk_print(
        f'Multiple dashboards with same {dashboard_filter} exist in the'
        f' project:{args.project}. Delete all but one dashboard deployed using'
        ' https://github.com/google/cloud-tpu-monitoring-debugging.'
    )
    return True, None

  if dashboards[0]:
    return False, dashboards[0].strip().split('/')[-1]

  return True, None


def get_gke_outlier_dashboard(args) -> str | None:
  """Get the identifier of GKE outlier dashboard deployed in the project.

  Args:
    args: user provided arguments for running the command.

  Returns:
    str:
      identifier of outlier dashboard if deployed in project,
      None otherwise.
  """
  outlier_dashboard_filter = "displayName:'GKE - TPU Monitoring Dashboard'"
  is_error, dashboard_id = get_gke_dashboard(args, outlier_dashboard_filter)

  # 'gcloud monitoring dashboards list' returned an error or multiple dashboards with same filter exist in the project
  if is_error:
    return None

  # 'gcloud monitoring dashboards list' succeeded but no dashboard for the filter exist in the project
  if not is_error and not dashboard_id:
    xpk_print(
        'Follow https://github.com/google/cloud-tpu-monitoring-debugging to'
        ' deploy monitoring dashboard to view statistics and outlier mode of'
        ' GKE metrics.'
    )
    return None

  return str(dashboard_id)


def get_gke_debugging_dashboard(args) -> str | None:
  """Get the identifier of GKE debugging dashboard deployed in the project.

  Args:
    args: user provided arguments for running the command.

  Returns:
    str:
      identifier of debugging dashboard if deployed in project,
      None otherwise.
  """
  debugging_dashboard_filter = "displayName:'GKE - TPU Logging Dashboard'"
  is_error, dashboard_id = get_gke_dashboard(args, debugging_dashboard_filter)

  # 'gcloud monitoring dashboards list' returned an error or multiple dashboards with same filter exist in the project
  if is_error:
    return None

  # 'gcloud monitoring dashboards list' succeeded but no dashboard for the filter exist in the project
  if not is_error and not dashboard_id:
    xpk_print(
        'Follow https://github.com/google/cloud-tpu-monitoring-debugging to'
        ' deploy debugging dashboard to view stack traces collected in Cloud'
        ' Logging.'
    )
    return None

  return str(dashboard_id)
