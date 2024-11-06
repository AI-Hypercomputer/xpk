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
from ..utils import xpk_print, write_tmp_file
from .commands import run_command_for_value, run_kubectl_apply
from enum import Enum

import tempfile
from os import mkdir
from os.path import join

import urllib.request
from urllib.error import ContentTooShortError
import os


class AppProfileDefaults(Enum):
  NAME = "xpk-def-app-profile"


class JobTemplateDefaults(Enum):
  NAME = "xpk-def-batch"
  PARALLELISM = 1
  COMPLETIONS = 1
  CONTAINER_NAME = "xpk-batch-container"
  IMAGE = "ubuntu:22.04"


class PodTemplateDefaults(Enum):
  NAME = "xpk-def-pod"
  CONTAINER_NAME = "xpk-interactive-container"
  IMAGE = "busybox:1.28"


crd_file_urls = {
    "kjobctl.x-k8s.io_applicationprofiles.yaml": "https://raw.githubusercontent.com/kubernetes-sigs/kueue/refs/heads/main/cmd/experimental/kjobctl/config/crd/bases/kjobctl.x-k8s.io_applicationprofiles.yaml",
    "kjobctl.x-k8s.io_jobtemplates.yaml": "https://raw.githubusercontent.com/kubernetes-sigs/kueue/refs/heads/main/cmd/experimental/kjobctl/config/crd/bases/kjobctl.x-k8s.io_jobtemplates.yaml",
    "kjobctl.x-k8s.io_rayclustertemplates.yaml": "https://raw.githubusercontent.com/kubernetes-sigs/kueue/refs/heads/main/cmd/experimental/kjobctl/config/crd/bases/kjobctl.x-k8s.io_rayclustertemplates.yaml",
    "kjobctl.x-k8s.io_rayjobtemplates.yaml": "https://raw.githubusercontent.com/kubernetes-sigs/kueue/refs/heads/main/cmd/experimental/kjobctl/config/crd/bases/kjobctl.x-k8s.io_rayjobtemplates.yaml",
    "kjobctl.x-k8s.io_volumebundles.yaml": "https://raw.githubusercontent.com/kubernetes-sigs/kueue/refs/heads/main/cmd/experimental/kjobctl/config/crd/bases/kjobctl.x-k8s.io_volumebundles.yaml",
}

kustomization_url = {
    "kustomization.yaml": "https://raw.githubusercontent.com/kubernetes-sigs/kueue/refs/heads/main/cmd/experimental/kjobctl/config/crd/kustomization.yaml"
}

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
            - name: {container_name}
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
      template: {batch_template}
      requiredFlags: []
    - name: Interactive
      template: {interactive_template}
"""

pod_template_yaml = """
apiVersion: v1
kind: PodTemplate
metadata:
  name: {name}
  namespace: default
template:
  spec:
    containers:
      - name: {container_name}
        image: {image}
        command: ['/bin/sh']
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
  return run_kubectl_apply(
      yml_string=app_profile_yaml.format(
          name=AppProfileDefaults.NAME.value,
          batch_template=JobTemplateDefaults.NAME.value,
          interactive_template=PodTemplateDefaults.NAME.value,
      ),
      task="Creating AppProfile",
      args=args,
  )


def create_job_template_instance(args: Namespace) -> int:
  """Create new JobTemplate instance on cluster with default settings.

  Args:
    args - user provided arguments
  Returns:
    exit_code > 0 if creating JobTemplate fails, 0 otherwise
  """
  return run_kubectl_apply(
      yml_string=job_template_yaml.format(
          name=JobTemplateDefaults.NAME.value,
          parallelism=JobTemplateDefaults.PARALLELISM.value,
          completions=JobTemplateDefaults.COMPLETIONS.value,
          container_name=JobTemplateDefaults.CONTAINER_NAME.value,
          image=JobTemplateDefaults.IMAGE.value,
      ),
      task="Creating JobTemplate",
      args=args,
  )


def create_pod_template_instance(args: Namespace) -> int:
  """Create new PodTemplate instance on cluster with default settings.

  Args:
    args - user provided arguments
  Returns:
    exit_code > 0 if creating PodTemplate fails, 0 otherwise
  """
  return run_kubectl_apply(
      yml_string=pod_template_yaml.format(
          name=PodTemplateDefaults.NAME.value,
          container_name=PodTemplateDefaults.CONTAINER_NAME.value,
          image=PodTemplateDefaults.IMAGE.value,
      ),
      task="Creating PodTemplate",
      args=args,
  )


def download_crd_file_urls(files: dict[str, str], path: str) -> int:
  for file, url in files.items():
    try:
      target = os.path.join(path, file)
      urllib.request.urlretrieve(url, target)
    except ContentTooShortError as e:
      xpk_print(f"downloading kjob CDR file {file} failed due to {e.content}")
      return 1
  return 0


def prepare_kjob(args) -> int:
  job_err_code = create_job_template_instance(args)
  if job_err_code > 0:
    return job_err_code

  pod_err_code = create_pod_template_instance(args)
  if pod_err_code > 0:
    return pod_err_code

  return create_app_profile_instance(args)


def clear_kustomize_tmp(kjob_tmp: str) -> None:
  xpk_print("Cleaning kustomize tmp directory.")
  bases = join(kjob_tmp, "bases")
  for file in kustomization_url:
    os.remove(join(kjob_tmp, file))

  for file in crd_file_urls:
    os.remove(join(bases, file))

  os.rmdir(bases)
  os.rmdir(kjob_tmp)
  xpk_print("Cleaning kustomize tmp directory succeded.")


def apply_kjob_crds(args: Namespace) -> int:
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

  err_code = download_crd_file_urls(crd_file_urls, kustomize_bases)
  if err_code > 0:
    xpk_print("Downloading kjob CRDs failed.")
    return err_code

  err_code = download_crd_file_urls(kustomization_url, kjob_kustomize_path)
  if err_code > 0:
    xpk_print("Downloading kustomize file failed.")
    return err_code

  cmd = (
      f"kustomize build {kjob_kustomize_path} | kubectl apply --server-side"
      " -f -"
  )
  error_code, _ = run_command_for_value(
      cmd, "Create kjob CRDs on cluster", args
  )

  clear_kustomize_tmp(kjob_kustomize_path)
  if error_code != 0:
    xpk_print("Creating kjob CRDs on cluster failed.")
    return error_code
  xpk_print("Creating kjob CRDs succeded")
  return 0
