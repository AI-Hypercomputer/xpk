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


def job_info(args):
  """Run commands obtaining information about a job given by name.

  Args:
    args: user provided arguments for running the command.

  Returns:
    0 if successful and 1 otherwise.
  """
  command = f'kubectl-kjob describe slurm {args.name}'
  return_code, description = run_command_for_value(command, 'Getting job info', args)

  if return_code != 0:
    xpk_print(f'Job info request returned ERROR {return_code}')
    xpk_exit(return_code)

  spli_i = description.find('\nData\n====')
  job_desc_str = description[0:spli_i]
  slurm_desc_str = description[spli_i:]

  job_desc = yaml.safe_load(job_desc_str)

  profile = job_desc['Pod Template']['Containers']['xpk-container']['Environment']['PROFILE']
  labels = job_desc['Labels'].split(' ')
  mounts = job_desc['Pod Template']['Containers']['xpk-container']['Mounts']

  output = {
    'Profile': profile,
    'Labels': labels, 
    'Mounts': mounts,
  }

  formatted_output = yaml.safe_dump(output, default_flow_style=False, sort_keys=False)
  print(formatted_output)

  xpk_exit(0)
