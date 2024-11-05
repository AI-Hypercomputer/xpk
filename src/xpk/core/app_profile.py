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

from ..utils import xpk_exit, write_tmp_file
from .job_template import JOB_TEMPLATE_DEFAULT_NAME
from .commands import run_command_with_updates

APP_PROFILE_TEMPLATE_DEFAULT_NAME = "xpk-def-app-profile"
APP_PROFILE_TEMPLATE_MODE_NAME = "Slurm"

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


def create_app_profile_instance(args: Namespace) -> None:
  yml_string = app_profile_yaml.format(
      name=APP_PROFILE_TEMPLATE_DEFAULT_NAME,
      template=JOB_TEMPLATE_DEFAULT_NAME,
  )

  tmp = write_tmp_file(yml_string)
  command = f"kubectl apply -f {str(tmp.file.name)}"
  return_code = run_command_with_updates(command, "Creating AppProfile", args)
  if return_code != 0:
    xpk_exit(return_code)
