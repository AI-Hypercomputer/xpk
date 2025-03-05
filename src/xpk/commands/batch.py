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

from ..core.cluster import setup_k8s_env, create_k8s_service_account
from ..core.commands import run_command_for_value
from ..core.config import GCS_FUSE_ANNOTATION_KEY, GCS_FUSE_ANNOTATION_VALUE, XPK_SA, DEFAULT_NAMESPACE
from ..core.gcloud_context import add_zone_and_project
from ..core.kueue import LOCAL_QUEUE_NAME
from ..core.storage import get_auto_mount_gcsfuse_storages
from ..utils.console import xpk_exit, xpk_print
from .common import set_cluster_command
from ..core.kjob import AppProfileDefaults, prepare_kjob, Kueue_TAS_annotation, get_pod_template_annotations
from .kind import set_local_cluster_command
import re


def batch(args: Namespace) -> None:
  """Run batch task.
     This function runs passed script in non-blocking manner.
  Args:
    args: user provided arguments for running the command.
  Returns:
    None
  """
  if not args.kind_cluster:
    add_zone_and_project(args)
    set_cluster_command_code = set_cluster_command(args)
  else:
    set_cluster_command_code = set_local_cluster_command(args)

  if set_cluster_command_code != 0:
    xpk_exit(set_cluster_command_code)

  err_code = prepare_kjob(args)
  if err_code > 0:
    xpk_exit(err_code)

  submit_job(args)


def submit_job(args: Namespace) -> None:
  tcpxo, interfaces = get_pod_template_annotations(args)
  k8s_api_client = setup_k8s_env(args)
  create_k8s_service_account(XPK_SA, DEFAULT_NAMESPACE)
  gcs_fuse_storages = get_auto_mount_gcsfuse_storages(k8s_api_client)

  cmd = (
      'kubectl kjob create slurm  --profile'
      f' {AppProfileDefaults.NAME.value} \\\n --localqueue'
      f' {LOCAL_QUEUE_NAME} \\\n --pod-template-annotation'
      f' {Kueue_TAS_annotation} \\\n --pod-template-annotation {tcpxo} \\\n'
      ' --pod-template-annotation networking.gke.io/default-interface="eth0"'
      f' \\\n --pod-template-annotation {interfaces} \\\n --first-node-ip'
  )

  if len(gcs_fuse_storages) > 0:
    cmd += (
        ' --pod-template-annotation'
        f' {GCS_FUSE_ANNOTATION_KEY}={GCS_FUSE_ANNOTATION_VALUE}'
    )

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

  return_code, return_value = run_command_for_value(cmd, 'submit job', args)

  if return_code != 0:
    xpk_print(f'Running batch job returned ERROR {return_code}')
    xpk_exit(return_code)

  m = re.match(r'job\.batch/([-a-z0-9]+)', return_value)
  if m:
    xpk_print(f'Job name: {m.group(1)}')
