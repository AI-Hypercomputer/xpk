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

from .commands import run_command_with_updates_retry
from .core import zone_to_region
from .config import XpkConfig, GKE_ENDPOINT_KEY
from ..utils.console import xpk_print
import os

CONTAINER_API_ENDPOINT = 'CLOUDSDK_API_ENDPOINT_OVERRIDES_CONTAINER'


def get_cluster_credentials(args) -> int:
  """Run cluster configuration command to set the kubectl config.

  Args:
    args: user provided arguments for running the command.

  Returns:
    0 if successful and 1 otherwise.
  """
  set_gcloud_container_api_endpoint(args)

  command = (
      f'echo ${CONTAINER_API_ENDPOINT} && '
      'gcloud container clusters get-credentials'
      f' {args.cluster}  --region={zone_to_region(args.zone)}'
      f' --project={args.project} &&'
      ' kubectl config view && kubectl config set-context --current'
      ' --namespace=default'
  )
  task = f'get-credentials to cluster {args.cluster}'
  return_code = run_command_with_updates_retry(
      command, task, args, verbose=(args.gke_sandbox is not None)
  )
  if return_code != 0:
    xpk_print(f'{task} returned ERROR {return_code}')
  return return_code


def set_gcloud_container_api_endpoint(args):
  """Sets CLOUDSDK_API_ENDPOINT_OVERRIDES_CONTAINER environment variable for current process

  Args:
    args: user provided arguments for running the command.

  Returns:
    0 if successful and 1 otherwise.
  """
  gke_endpoint = XpkConfig().get(GKE_ENDPOINT_KEY)
  if gke_endpoint is not None and len(gke_endpoint) > 0:
    os.environ[CONTAINER_API_ENDPOINT] = gke_endpoint
