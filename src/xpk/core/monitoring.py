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


class GKEDashboardManager:
  """Handles retrieval of GKE dashboards."""

  def __init__(self, args):
    self.args = args

  def get_dashboard(self, dashboard_filter) -> str | None:
    """Get the identifier of GKE dashboard deployed in the project.

    Returns:
      str:
        identifier of dashboard if deployed in project,
        None otherwise.
    """
    command = (
        'gcloud monitoring dashboards list'
        f' --project={self.args.project} --filter="{dashboard_filter}"'
        ' --format="value(name)" --verbosity=error'
    )

    return_code, return_value = run_command_for_value(
        command, 'GKE Dashboard List', self.args
    )

    if return_code != 0:
      xpk_print(
          f'GKE Dashboard List request returned ERROR {return_code}. If there'
          ' is a permissions error, please check'
          ' https://github.com/google/xpk/blob/main/README.md#roles-needed-based-on-permission-errors'
          ' for possible solutions.'
      )
      return None

    if not return_value:
      xpk_print(
          f'No dashboard with {dashboard_filter} found in the'
          f' project:{self.args.project}.'
      )
      return None

    dashboards = return_value.strip().split('\n')
    if len(dashboards) > 1:
      xpk_print(
          f'Multiple dashboards with same {dashboard_filter} exist in the'
          f' project:{self.args.project}. Delete all but one dashboard deployed'
          ' using https://github.com/google/cloud-tpu-monitoring-debugging.'
      )
      return None

    return dashboards[0].strip().split('/')[-1] if dashboards[0] else None

  def get_outlier_dashboard(self) -> str | None:
    """Get the identifier of GKE outlier dashboard deployed in the project.

    Returns:
      str:
        identifier of outlier dashboard if deployed in project,
        None otherwise.
    """
    return self.get_dashboard("displayName:'GKE - TPU Monitoring Dashboard'")

  def get_debugging_dashboard(self) -> str | None:
    """Get the identifier of GKE debugging dashboard deployed in the project.

    Returns:
      str:
        identifier of debugging dashboard if deployed in project,
        None otherwise.
    """
    return self.get_dashboard("displayName:'GKE - TPU Logging Dashboard'")
