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
from ..utils import xpk_print, xpk_exit, write_tmp_file
from .commands import run_command_for_value, run_command_with_updates
import urllib.request
import tempfile
from os import mkdir
from os.path import join
from ..core.commands import (
    run_command_for_value,
)


APP_PROFILE_TEMPLATE_DEFAULT_NAME = "xpk-def-app-profile"
APP_PROFILE_TEMPLATE_MODE_NAME = "Slurm"

JOB_TEMPLATE_DEFAULT_NAME = "xpk-def-batch"
JOB_TEMPLATE_DEFAULT_PARALLELISM = 1
JOB_TEMPLATE_DEFAULT_COMPLETIONS = 1
JOB_TEMPLATE_DEFAULT_COMPLETION_MODE = "Indexed"
JOB_TEMPLATE_DEFAULT_CONT_NAME = "xpk-container"
JOB_TEMPLATE_DEFAULT_IMG = "ubuntu:22.04"

app_profile_gh_file = "https://raw.githubusercontent.com/kubernetes-sigs/kueue/refs/heads/main/cmd/experimental/kjobctl/config/crd/bases/kjobctl.x-k8s.io_applicationprofiles.yaml"
job_template_gh_file = "https://raw.githubusercontent.com/kubernetes-sigs/kueue/refs/heads/main/cmd/experimental/kjobctl/config/crd/bases/kjobctl.x-k8s.io_jobtemplates.yaml"
ray_cluster_gh_file = "https://raw.githubusercontent.com/kubernetes-sigs/kueue/refs/heads/main/cmd/experimental/kjobctl/config/crd/bases/kjobctl.x-k8s.io_rayclustertemplates.yaml"
ray_job_tmpl_gh_file = "https://raw.githubusercontent.com/kubernetes-sigs/kueue/refs/heads/main/cmd/experimental/kjobctl/config/crd/bases/kjobctl.x-k8s.io_rayjobtemplates.yaml"
volume_bundles_gh_file = "https://raw.githubusercontent.com/kubernetes-sigs/kueue/refs/heads/main/cmd/experimental/kjobctl/config/crd/bases/kjobctl.x-k8s.io_volumebundles.yaml"
customization_gh_file = "https://raw.githubusercontent.com/kubernetes-sigs/kueue/refs/heads/main/cmd/experimental/kjobctl/config/crd/kustomization.yaml"

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


def verify_kjob_installed(args: Namespace) -> None:
  """Check if kjob is installed. If not provide user with proper communicate and exit.
  Args:
  Returns:
    None
  """
  command = "kubectl-kjob help"
  task = "Verify kjob installation "
  verify_kjob_installed_code, _ = run_command_for_value(command, task, args)

  if verify_kjob_installed_code == 0:
    xpk_print("kjob found")

  if verify_kjob_installed_code != 0:
    xpk_print(
        " kjob not found. Please follow"
        " https://github.com/kubernetes-sigs/kueue/blob/main/cmd/experimental/kjobctl/docs/installation.md"
        " to install kjob."
    )
    xpk_exit(verify_kjob_installed_code)


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


def create_job_template_instance(args: Namespace) -> None:
  yml_string = job_template_yaml.format(
      name=JOB_TEMPLATE_DEFAULT_NAME,
      parallelism=JOB_TEMPLATE_DEFAULT_PARALLELISM,
      completions=JOB_TEMPLATE_DEFAULT_COMPLETIONS,
      container=JOB_TEMPLATE_DEFAULT_CONT_NAME,
      image=JOB_TEMPLATE_DEFAULT_IMG,
  )

  tmp = write_tmp_file(yml_string)
  command = f"kubectl apply -f {str(tmp.file.name)}"
  return_code = run_command_with_updates(command, "Creating JobTemplate", args)
  if return_code != 0:
    xpk_exit(return_code)


def download_files_from_github_into_dir(
    path: str, urls: list[(str, str)]
) -> str:
  for url, fn in urls:
    target = join(path, fn)
    urllib.request.urlretrieve(url, target)


def apply_kjob_crds(args):
  temp_dir = tempfile.mkdtemp()
  mkdir(join(temp_dir, "bases"))
  urls = [
      job_template_gh_file,
      ray_cluster_gh_file,
      ray_job_tmpl_gh_file,
      volume_bundles_gh_file,
      app_profile_gh_file,
  ]
  download_files_from_github_into_dir(
      join(temp_dir, "bases"), list(zip(urls, [url.rsplit("/", maxsplit=1)[-1] for url in urls]))
  )
  download_files_from_github_into_dir(
      temp_dir, [(customization_gh_file, "kustomization.yaml")]
  )

  cmd = f"kustomize build {temp_dir} | kubectl apply --server-side -f -"
  error_code, _ = run_command_for_value(cmd, "Create kjob CRDs on cluster", args)
  if error_code != 0:
    exit(error_code)

  xpk_print('Creating kjob CRDs succeded')