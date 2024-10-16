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

from argparse import Namespace
from ..utils import xpk_exit, xpk_print
from .cluster import set_cluster_command
from ..core.core import (add_zone_and_project, setup_k8s_env)
from argparse import Namespace
from kubernetes import client as k8s_client
from ..core.job_template import create_job_template_instance
from ..core.app_profile import create_app_profile_instance
from ..core.app_profile import APP_PROFILE_TEMPLATE_DEFAULT_NAME
from ..core.commands import (
    run_command_for_value,
)


def batch(args: Namespace) -> None:
  """Run batch task.
     This function runs passed script in non-blocking manner.
  Args:
    args: user provided arguments for running the command.
  Returns:
    None
  """
  add_zone_and_project(args)
  set_cluster_command_code = set_cluster_command(args)
  if set_cluster_command_code != 0:
    xpk_exit(set_cluster_command_code)

  k8s_api_client = setup_k8s_env(args)
  create_job_template(k8s_api_client, args)
  create_app_profile(k8s_api_client, args)
  submit_job(args)


def create_job_template(k8s_api_client, args: Namespace) -> None:
  create_job_template_instance(k8s_api_client, args)


def create_app_profile(k8s_api_client, args: Namespace) -> None:
  create_app_profile_instance(k8s_api_client, args)


def submit_job(args: Namespace) -> None:
  cmd = (
      'kubectl-kjob create slurm --profile'
      f' {APP_PROFILE_TEMPLATE_DEFAULT_NAME} --'
      f' {args.script} {args.script_args}'
  )
  return_code, val = run_command_for_value(cmd, 'submit job', args)

  if return_code != 0:
    xpk_print(f'Cluster info request returned ERROR {return_code}')
    xpk_exit(return_code)
  print(val)
