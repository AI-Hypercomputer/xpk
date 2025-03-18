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

import re
import sys

from ruamel.yaml import YAML

from ..core.commands import run_command_for_value, run_command_with_updates
from ..core.gcloud_context import add_zone_and_project
from ..core.kjob import AppProfileDefaults
from ..utils.console import xpk_exit, xpk_print
from .common import set_cluster_command
from .kind import set_local_cluster_command


def job_info(args):
  """Run commands obtaining information about a job given by name.

  Args:
    args: user provided arguments for running the command.

  Returns:
    None
  """
  job_name = args.name

  desc_command = f'kubectl-kjob describe slurm {job_name}'
  desc_code, desc_text = run_command_for_value(
      desc_command, 'Getting job data', args
  )
  if desc_code != 0:
    xpk_print(f'Data info request returned ERROR {desc_code}')
    xpk_exit(desc_code)

  job_command = (
      'kubectl-kjob list slurm -o yaml --field-selector'
      f' metadata.name=={job_name}'
  )
  job_code, job_text = run_command_for_value(
      job_command, 'Getting job info', args
  )
  if job_code != 0:
    xpk_print(f'Job info request returned ERROR {job_code}')
    xpk_exit(job_code)

  pods_command = f'kubectl get pods -l=job-name={job_name} --no-headers'
  pods_code, pods_text = run_command_for_value(
      pods_command, 'Getting pods list', args
  )
  if pods_code != 0:
    xpk_print(f'Pods list request returned ERROR {pods_code}')
    xpk_exit(pods_code)

  yaml = YAML(typ='safe')
  job_yaml = yaml.load(job_text)['items'][0]

  output = {
      'Job name': job_name,
      'Script name': get_script_name(job_yaml),
      'Profile': get_profile(job_yaml),
      'Labels': job_yaml.get('metadata').get('labels', []),
      'Mounts': get_mounts(job_yaml),
      'Pods': get_pods(pods_text),
      'Entrypoint environment variables template': get_kjob_env_vars(desc_text),
  }

  yaml.default_flow_style = False
  yaml.sort_base_mapping_type_on_output = False
  yaml.dump(output, sys.stdout)


def get_profile(job_yaml: dict) -> str:
  containers = (
      job_yaml.get('spec', {})
      .get('template', {})
      .get('spec', {})
      .get('containers', [])
  )
  env_vars = next(iter(containers), {}).get('env', [])
  profile = next((x['value'] for x in env_vars if x['name'] == 'PROFILE'), '')
  return profile


def get_mounts(job_yaml: dict) -> list[dict]:
  containers = (
      job_yaml.get('spec', {})
      .get('template', {})
      .get('spec', {})
      .get('containers', [])
  )
  mounts = next(iter(containers), {}).get('volumeMounts', [])
  return mounts


def get_kjob_env_vars(job_desc_text: str) -> list[tuple[str, str]]:
  regex = r'(SLURM_[A-Z_]*=.*)'
  search_res = re.findall(regex, job_desc_text)
  return search_res


def get_pods(pods_text: str) -> list[str]:
  pods_lines = pods_text.strip().split('\n')
  pods_lines = [line.split() for line in pods_lines]
  return [
      {
          'Name': line[0],
          'Status': line[2],
      }
      for line in pods_lines
  ]


def get_script_name(job_yaml: dict) -> str | None:
  return (
      job_yaml.get('metadata', {})
      .get('annotations', {})
      .get('kjobctl.x-k8s.io/script', '')
  )


def job_list(args) -> None:
  """Function around job list.

  Args:
    args: user provided arguments for running the command.

  Returns:
    None
  """
  if not args.kind_cluster:
    add_zone_and_project(args)
    set_cluster_command_code = set_cluster_command(args)
    msg = f'Listing jobs for project {args.project} and zone {args.zone}:'
  else:
    set_cluster_command_code = set_local_cluster_command(args)
    msg = 'Listing jobs:'

  if set_cluster_command_code != 0:
    xpk_exit(set_cluster_command_code)
  xpk_print(msg, flush=True)

  return_code = run_slurm_job_list_command(args)
  xpk_exit(return_code)


def run_slurm_job_list_command(args) -> int:
  cmd = f'kubectl-kjob list slurm  --profile {AppProfileDefaults.NAME.value}'

  return_code = run_command_with_updates(cmd, 'list jobs', args)
  if return_code != 0:
    xpk_print(f'Listing jobs returned ERROR {return_code}')
  return return_code


def job_cancel(args) -> None:
  """Function around job cancel.

  Args:
    args: user provided arguments for running the command.

  Returns:
    None
  """
  xpk_print(f'Starting job cancel for job: {args.name}', flush=True)
  if not args.kind_cluster:
    add_zone_and_project(args)
    set_cluster_command_code = set_cluster_command(args)
  else:
    set_cluster_command_code = set_local_cluster_command(args)

  if set_cluster_command_code != 0:
    xpk_exit(set_cluster_command_code)

  return_code = run_slurm_job_delete_command(args)
  xpk_exit(return_code)


def run_slurm_job_delete_command(args) -> int:
  list_of_jobs = ' '.join(args.name)
  cmd = f'kubectl-kjob delete slurm {list_of_jobs}'

  return_code = run_command_with_updates(cmd, 'delete job', args)
  if return_code != 0:
    xpk_print(f'Delete job request returned ERROR {return_code}')
  return return_code
