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

from argparse import Namespace

from ..core.cluster import (
    setup_k8s_service_accounts,
    get_cluster_credentials,
)
from ..core.commands import run_command_with_full_controls
from ..core.gcloud_context import add_zone_and_project
from ..core.kjob import (
    AppProfileDefaults,
    JobTemplateDefaults,
    get_storage_annotations,
    prepare_kjob,
)
from ..core.kueue import LOCAL_QUEUE_NAME
from ..utils.console import xpk_exit, xpk_print
from .kind import set_local_cluster_command
from .kjob_common import add_gpu_networking_annotations_to_command, add_TAS_annotations_to_command


def run(args: Namespace) -> None:
  """Run task.
     This function runs passed script in non-blocking manner.
  Args:
    args: user provided arguments for running the command.
  Returns:
    None
  """
  if not args.kind_cluster:
    add_zone_and_project(args)
    get_cluster_credentials(args)
  else:
    set_cluster_command_code = set_local_cluster_command(args)
    if set_cluster_command_code != 0:
      xpk_exit(set_cluster_command_code)

  err_code = prepare_kjob(args)
  if err_code > 0:
    xpk_exit(err_code)
  setup_k8s_service_accounts()

  submit_job(args)


def submit_job(args: Namespace) -> None:
  cmd = (
      'kubectl kjob create slurm --profile'
      f' {AppProfileDefaults.NAME.value} '
      f' --localqueue {LOCAL_QUEUE_NAME} '
      f' --stream-container {JobTemplateDefaults.CONTAINER_NAME.value}'
      f' --worker-container {JobTemplateDefaults.CONTAINER_NAME.value}'
      ' --wait --rm  --first-node-ip'
  )
  cmd = add_gpu_networking_annotations_to_command(args, cmd)
  cmd = add_TAS_annotations_to_command(args, cmd)

  for annotation in get_storage_annotations(args):
    cmd += f' --pod-template-annotation {annotation}'

  if args.timeout:
    cmd += f' --wait-timeout {args.timeout}s'

  if args.ignore_unknown_flags:
    cmd += ' --ignore-unknown-flags'

  cmd += f' -- {args.script} --partition {LOCAL_QUEUE_NAME}'

  if args.array is not None:
    cmd += f' --array {args.array}'

  if args.cpus_per_task is not None:
    cmd += f' --cpus-per-task {args.cpus_per_task}'

  if args.gpus_per_task is not None:
    cmd += f' --gpus-per-task {args.gpus_per_task}'

  if args.mem is not None:
    cmd += f' --mem {args.mem}'

  if args.mem_per_task is not None:
    cmd += f' --mem-per-task {args.mem_per_task}'

  if args.mem_per_cpu is not None:
    cmd += f' --mem-per-cpu {args.mem_per_cpu}'

  if args.mem_per_gpu is not None:
    cmd += f' --mem-per-gpu {args.mem_per_gpu}'

  if args.nodes is not None:
    cmd += f' --nodes {args.nodes}'

  if args.ntasks is not None:
    cmd += f' --ntasks {args.ntasks}'

  if args.output is not None:
    cmd += f' --output {args.output}'

  if args.error is not None:
    cmd += f' --error {args.error}'

  if args.input is not None:
    cmd += f' --input {args.input}'

  if args.job_name is not None:
    cmd += f' --job-name {args.job_name}'

  if args.chdir is not None:
    cmd += f' --chdir {args.chdir}'

  if args.time is not None:
    cmd += f' --time {args.time}'

  return_code = run_command_with_full_controls(cmd, 'run task', args)

  if return_code != 0:
    xpk_print(f'Running task returned ERROR {return_code}')
    xpk_exit(return_code)
