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
from .capacity import DeviceType
from .commands import (
    run_command_for_value,
    run_command_with_updates,
    run_command_with_updates_retry,
)
from .gcloud_context import GCloudContextManager
from .system_characteristics import SystemCharacteristics

JOBSET_VERSION = 'v0.7.2'


class ClusterManager:
  """Manages Jobset and NCCL installation on Kubernetes clusters."""

  def __init__(self, args, system: SystemCharacteristics):
    self.args = args
    self.system = system

  # TODO(vbarr): Remove this function when jobsets gets enabled by default on
  # GKE clusters.
  def set_jobset_on_cluster(self) -> int:
    """Add jobset command on server side and ask user to verify it is created.

    Returns:
      0 if successful and 1 otherwise.
    """
    command = (
        'kubectl apply --server-side -f'
        f' https://github.com/kubernetes-sigs/jobset/releases/download/{JOBSET_VERSION}/manifests.yaml'
    )
    task = f'Install Jobset on {self.args.cluster}'
    return_code = run_command_with_updates_retry(command, task, self.args)

    if return_code != 0:
      xpk_print(f'{task} returned with ERROR {return_code}.\n')
      xpk_print(
          "This LIKELY means you're missing Kubernetes Permissions, you can"
          ' validate this by checking if the error references permission'
          ' problems such as `requires one of ["container.*"] permission(s)`.'
          ' Follow our readme:'
          ' https://github.com/google/xpk/blob/main/README.md#troubleshooting'
          ' for instructions on how to fix these permissions.'
      )
    return return_code

  def install_nccl_on_cluster(self) -> int:
    """Install NCCL plugin on the cluster.

    Returns:
      0 if successful and 1 otherwise.
    """
    nccl_url = (
        'https://raw.githubusercontent.com/GoogleCloudPlatform/container-engine-accelerators/master/gpudirect-tcpx/nccl-tcpx-installer.yaml'
        if self.system.device_type == DeviceType.H100.value
        else 'https://raw.githubusercontent.com/GoogleCloudPlatform/container-engine-accelerators/master/gpudirect-tcpxo/nccl-tcpxo-installer.yaml'
    )

    command = f'kubectl apply -f {nccl_url}'

    return_code = run_command_with_updates(
        command, 'Install NCCL Plugin On Cluster', self.args
    )
    if return_code != 0:
      xpk_print(
          f'Install NCCL Plugin On Cluster request returned ERROR {return_code}'
      )
      return 1

    return 0

  def get_all_clusters(self) -> tuple[list[str], int]:
    """Gets all the clusters associated with the project / region.

    Args:
      args: user provided arguments for running the command.

    Returns:
      List of cluster names and 0 if successful and 1 otherwise.
    """
    region = GCloudContextManager.zone_to_region(self.args.zone)
    command = (
        'gcloud container clusters list'
        f' --project={self.args.project} --region={region}'
        ' --format="csv[no-heading](name)"'
    )
    return_code, raw_cluster_output = run_command_for_value(
        command, 'Find if Cluster Exists', self.args
    )
    if return_code != 0:
      xpk_print(f'Find if Cluster Exists returned ERROR {return_code}')
      return [], return_code

    return raw_cluster_output.splitlines(), 0
