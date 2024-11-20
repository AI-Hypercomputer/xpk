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
from ..utils.console import xpk_print
from ..utils.file import write_tmp_file
from .commands import run_command_with_updates

from ..core.commands import (
    run_command_for_value,
)

# AppProfile defaults
APP_PROFILE_TEMPLATE_DEFAULT_NAME = "xpk-def-app-profile"

# JobTemplate defaults
JOB_TEMPLATE_DEFAULT_NAME = "xpk-def-batch"
JOB_TEMPLATE_DEFAULT_PARALLELISM = 1
JOB_TEMPLATE_DEFAULT_COMPLETIONS = 1
JOB_TEMPLATE_DEFAULT_CONT_NAME = "xpk-container"
JOB_TEMPLATE_DEFAULT_IMG = "ubuntu:22.04"

job_template_yaml = """
  apiVersion: kjobctl.x-k8s.io/v1alpha1
  kind: JobTemplate
  metadata:
    name: {name}
    namespace: default
  template:
    spec:
      parallelism: {parallelism}
      completions: {completions}
      completionMode: Indexed
      template:
        spec:
          containers:
            - name: {container}
              image: {image}
          restartPolicy: OnFailure"""

app_profile_yaml = """
apiVersion: kjobctl.x-k8s.io/v1alpha1
kind: ApplicationProfile
metadata:
  name: {name}
  namespace: default
spec:
  supportedModes:
    - name: Slurm
      template: {template}
      requiredFlags: []
"""


def verify_kjob_installed(args: Namespace) -> int:
  """Check if kjob is installed. If not provide user with proper communicate and exit.
  Args:
    args - user provided arguments.
  Returns:
    error code > if kjob not installed, otherwise 0
  """
  command = "kubectl-kjob help"
  task = "Verify kjob installation "
  verify_kjob_installed_code, _ = run_command_for_value(command, task, args)

  if verify_kjob_installed_code == 0:
    xpk_print("kjob found")
    return 0

  if verify_kjob_installed_code != 0:
    xpk_print(
        " kjob not found. Please follow"
        " https://github.com/kubernetes-sigs/kueue/blob/main/cmd/experimental/kjobctl/docs/installation.md"
        " to install kjob."
    )
    return verify_kjob_installed_code
  return 0


def create_app_profile_instance(args: Namespace) -> int:
  """Create new AppProfile instance on cluster with default settings.

  Args:
    args - user provided arguments
  Returns:
    exit_code > 0 if creating AppProfile fails, 0 otherwise
  """
  yml_string = app_profile_yaml.format(
      name=APP_PROFILE_TEMPLATE_DEFAULT_NAME,
      template=JOB_TEMPLATE_DEFAULT_NAME,
  )

  tmp = write_tmp_file(yml_string)
  command = f"kubectl apply -f {str(tmp.file.name)}"
  err_code = run_command_with_updates(command, "Creating AppProfile", args)
  if err_code != 0:
    return err_code
  return 0


def create_job_template_instance(args: Namespace) -> int:
  """Create new JobTemplate instance on cluster with default settings.

  Args:
    args - user provided arguments
  Returns:
    exit_code > 0 if creating JobTemplate fails, 0 otherwise
  """
  yml_string = job_template_yaml.format(
      name=JOB_TEMPLATE_DEFAULT_NAME,
      parallelism=JOB_TEMPLATE_DEFAULT_PARALLELISM,
      completions=JOB_TEMPLATE_DEFAULT_COMPLETIONS,
      container=JOB_TEMPLATE_DEFAULT_CONT_NAME,
      image=JOB_TEMPLATE_DEFAULT_IMG,
  )

  tmp = write_tmp_file(yml_string)
  command = f"kubectl apply -f {str(tmp.file.name)}"
  err_code = run_command_with_updates(command, "Creating JobTemplate", args)
  if err_code != 0:
    return err_code
  return 0


def prepare_kjob(args) -> int:
  err_code = create_job_template_instance(args)
  if err_code > 0:
    return err_code
  return create_app_profile_instance(args)


def apply_kjob_crds(args: Namespace) -> int:
  """Apply kjob CRDs on cluster.

  This function install kjob CRDs files from kjobctl printcrds.
  It creates all neccessary kjob CRDs.

  Args:
    args - user provided arguments
  Returns:
    None
  """
  command = "kubectl kjob printcrds | kubectl apply --server-side -f -"
  task = "Create kjob CRDs on cluster"
  return_code = run_command_with_updates(command, task, args)
  if return_code != 0:
    xpk_print(f"{task} returned ERROR {return_code}")
    return return_code
  xpk_print("Creating kjob CRDs succeded")
  return 0
