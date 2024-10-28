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

import tempfile
from os import mkdir, rmdir
from os.path import join
from ..core.commands import (
    run_command_for_value,
)
from .utils import download_files_from_github_into_dir

# AppProfile defaults
APP_PROFILE_TEMPLATE_DEFAULT_NAME = "xpk-def-app-profile"

# JobTemplate defaults
JOB_TEMPLATE_DEFAULT_NAME = "xpk-def-batch"
JOB_TEMPLATE_DEFAULT_PARALLELISM = 1
JOB_TEMPLATE_DEFAULT_COMPLETIONS = 1
JOB_TEMPLATE_DEFAULT_CONT_NAME = "xpk-container"
JOB_TEMPLATE_DEFAULT_IMG = "ubuntu:22.04"

# kjob CRDs
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
    args - user provided arguments.
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
  """Create new AppProfile instance on cluster with default settings.

  Args:
    args - user provided arguments
  Returns:
    None
  """
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
  """Create new JobTemplate instance on cluster with default settings.

  Args:
    args - user provided arguments
  Returns:
    None
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
  return_code = run_command_with_updates(command, "Creating JobTemplate", args)
  if return_code != 0:
    xpk_exit(return_code)


def apply_kjob_crds(args: Namespace) -> None:
  """Apply kjob CRDs on cluster.

  This function downloads kjob CRDs files from kjob repo,
  builds them with kustomize and then applies result on cluster.
  It creates all neccessary kjob CRDs.

  Args:
    args - user provided arguments
  Returns:
    None
  """
  kjob_kustomize_path = tempfile.mkdtemp()
  kustomize_bases = join(kjob_kustomize_path, "bases")
  mkdir(kustomize_bases)
  urls = [
      job_template_gh_file,
      ray_cluster_gh_file,
      ray_job_tmpl_gh_file,
      volume_bundles_gh_file,
      app_profile_gh_file,
  ]
  download_files_from_github_into_dir(
      kustomize_bases,
      list(zip(urls, [url.rsplit("/", maxsplit=1)[-1] for url in urls])),
  )
  download_files_from_github_into_dir(
      kjob_kustomize_path, [(customization_gh_file, "kustomization.yaml")]
  )

  cmd = (
      f"kustomize build {kjob_kustomize_path} | kubectl apply --server-side"
      " -f -"
  )
  error_code, _ = run_command_for_value(
      cmd, "Create kjob CRDs on cluster", args
  )
  rmdir(kjob_kustomize_path)
  if error_code != 0:
    xpk_exit(error_code)

  xpk_print("Creating kjob CRDs succeded")
