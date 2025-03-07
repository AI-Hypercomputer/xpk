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

from ..core.commands import run_command_with_full_controls, run_command_for_value, run_command_with_updates
from ..core.cluster import get_cluster_credentials, add_zone_and_project, create_xpk_k8s_service_account
from ..utils.console import xpk_exit, xpk_print
from argparse import Namespace

from ..core.kjob import (
    AppProfileDefaults,
    prepare_kjob,
    get_pod_template_interactive_command,
    get_gcsfuse_annotation,
)

exit_instructions = 'To exit the shell input "exit".'


def shell(args: Namespace):
  """Enter interactive shell.
  Args:
    args: user provided arguments for running the command.
  Returns:
    0 if successful and 1 otherwise.
  """
  exisitng_shell_pod_name = get_existing_shell_pod_name(args)

  if exisitng_shell_pod_name is None:
    return_code = connect_to_new_interactive_shell(args)
  else:
    return_code = connect_to_existing_interactive_shell(
        exisitng_shell_pod_name, args
    )

  if return_code != 0:
    xpk_print(f'The command failed with code {return_code}.')
    xpk_exit(return_code)

  xpk_exit(0)


def get_existing_shell_pod_name(args: Namespace) -> str | None:
  if not args.kind_cluster:
    add_zone_and_project(args)
    get_cluster_credentials(args)

  return_code, shell_name = run_command_for_value(
      command=(
          'kubectl get pods --no-headers --field-selector status.phase=Running'
          ' -o custom-columns=":metadata.name"'
      ),
      task='Get existing interactive shell pod name.',
      global_args=args,
  )
  if return_code != 0:
    xpk_print(
        f'Encounter an error with a code {return_code} when checking for'
        ' existing running shell.'
    )
    xpk_exit(return_code)

  pod_names = shell_name.strip().split('\n')
  kjob_pod_names = [
      name for name in pod_names if AppProfileDefaults.NAME.value in name
  ]
  shell_pod_names = [name for name in kjob_pod_names if 'interactive' in name]

  return shell_pod_names[0] if shell_pod_names else None


def connect_to_new_interactive_shell(args: Namespace) -> int:
  err_code = prepare_kjob(args)
  if err_code > 0:
    xpk_exit(err_code)
  create_xpk_k8s_service_account()

  cmd = (
      'kubectl-kjob create interactive --profile'
      f' {AppProfileDefaults.NAME.value} --pod-running-timeout 180s'
  )

  gcsfuse_annotation = get_gcsfuse_annotation(args)
  if gcsfuse_annotation is not None:
    cmd += f' --pod-template-annotation {gcsfuse_annotation}'

  return run_command_with_full_controls(
      command=cmd,
      task='Creating new interactive shell and entering it',
      global_args=args,
      instructions=exit_instructions,
  )


def connect_to_existing_interactive_shell(
    pod_name: str, args: Namespace
) -> int:
  return run_command_with_full_controls(
      command=(
          f'kubectl exec --stdin --tty {pod_name} --'
          f' {get_pod_template_interactive_command()}'
      ),
      task='Entering existing interactive shell',
      global_args=args,
      instructions=exit_instructions,
  )


def shell_stop(args: Namespace):
  """Stop the running interactive shell by deleting the pod.
  Args:
    args: user provided arguments for running the command.
  Returns:
    0 if successful and 1 otherwise.
  """
  exisitng_shell_pod_name = get_existing_shell_pod_name(args)

  if exisitng_shell_pod_name is None:
    xpk_print('There is no shell running to stop')
    xpk_exit(0)

  return_code = run_command_with_updates(
      command=f'kubectl delete pod {exisitng_shell_pod_name}',
      task='Deleting the existing shell.',
      global_args=args,
  )
  if return_code != 0:
    xpk_exit(return_code)

  xpk_print('The shell was deleted successfully.')
  xpk_exit(0)
