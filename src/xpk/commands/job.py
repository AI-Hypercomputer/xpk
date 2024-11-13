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

from ..core.commands import run_command_for_value
from ..utils import xpk_exit, xpk_print
import yaml
import re


def job_info(args):
  """Run commands obtaining information about a job given by name.

  Args:
    args: user provided arguments for running the command.

  Returns:
    0 if successful and 1 otherwise.
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

  job_yaml = yaml.safe_load(job_text)['items'][0]

  output = {
      'Job name': job_name,
      'Profile': get_profile(job_yaml),
      'Labels': job_yaml['metadata']['labels'],
      'Mounts': job_yaml['spec']['template']['spec']['containers'][0][
          'volumeMounts'
      ],
      'Environment variables': get_ev_vars(desc_text),
      'Pods': get_pods(pods_text),
  }

  formatted_output = yaml.dump(
      output, default_flow_style=False, sort_keys=False
  )
  xpk_print(formatted_output.strip())

  xpk_exit(0)


def get_profile(job_yaml: dict) -> str:
  env_vars = job_yaml['spec']['template']['spec']['containers'][0]['env']
  profile = next((x['value'] for x in env_vars if x['name'] == 'PROFILE'), '')
  return profile


def get_ev_vars(job_desc_text: str) -> list[tuple[str, str]]:
  regex = r'(SLURM_[A-Z_]*=.*)'
  search_res = re.findall(regex, job_desc_text)
  return search_res


def get_pods(pods_text: str) -> list[str]:
  pods_lines = pods_text.strip().split('\n')
  return [line.split()[0] for line in pods_lines]
