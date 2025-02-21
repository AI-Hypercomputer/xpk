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
from .commands import run_command_for_value, run_kubectl_apply, run_command_with_updates
from .config import XpkConfig, KJOB_SHELL_IMAGE, KJOB_SHELL_INTERACTIVE_COMMAND, KJOB_BATCH_IMAGE
from .resources import get_cluster_system_characteristics, SystemCharacteristics, AcceleratorType
from enum import Enum


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
  INTERACTIVE_COMMAND = "/bin/sh"


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
          tolerations:
            - operator: "Exists"
              key: nvidia.com/gpu
          containers:
            - name: {container_name}
              image: {image}
              {resources}
          {node_selector}
          restartPolicy: OnFailure"""
job_node_selector_template = """
          nodeSelector:
            cloud.google.com/gke-accelerator: {gpu_name}
"""
job_resources_template = """
              resources:
                limits:
                  nvidia.com/gpu: {gpu_per_node}
"""

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
    tolerations:
      - effect: NoSchedule
        key: components.gke.io/gke-managed-components
        operator: Equal
        value: "true"
    containers:
      - name: {container_name}
        image: {image}
        command: [{interactive_command}]
"""

Kueue_TAS_annotation = "kueue.x-k8s.io/podset-preferred-topology=cloud.google.com/gce-topology-host"


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
        " https://github.com/kubernetes-sigs/kjob/blob/main/docs/installation.md"
        " to install kjob."
    )
    return verify_kjob_installed_code
  return 0


def get_pod_template_interactive_command() -> str:
  """Gets the interactive command for PodTemplate from config otherwise the default value.

  Args:
    args - user provided arguments
  Returns:
    str - PodTemplate's interactive command
  """
  config = XpkConfig()
  pod_command = config.get(KJOB_SHELL_INTERACTIVE_COMMAND)
  if pod_command is None or len(pod_command) == 0:
    pod_command = PodTemplateDefaults.INTERACTIVE_COMMAND.value

  return pod_command


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


def create_job_template_instance(
    args: Namespace, system: SystemCharacteristics | None
) -> int:
  """Create new JobTemplate instance on cluster with default settings.

  Args:
    args - user provided arguments
  Returns:
    exit_code > 0 if creating JobTemplate fails, 0 otherwise
  """
  config = XpkConfig()
  job_image = config.get(KJOB_BATCH_IMAGE)
  if job_image is None or len(job_image) == 0:
    job_image = JobTemplateDefaults.IMAGE.value

  resources = (
      job_resources_template.format(gpu_per_node=system.chips_per_vm)
      if system is not None
      and system.accelerator_type == AcceleratorType["GPU"]
      else ""
  )

  node_selector = (
      job_node_selector_template.format(gpu_name=system.gke_accelerator)
      if system is not None
      and system.accelerator_type == AcceleratorType["GPU"]
      else ""
  )

  return run_kubectl_apply(
      yml_string=job_template_yaml.format(
          name=JobTemplateDefaults.NAME.value,
          parallelism=JobTemplateDefaults.PARALLELISM.value,
          completions=JobTemplateDefaults.COMPLETIONS.value,
          container_name=JobTemplateDefaults.CONTAINER_NAME.value,
          image=job_image,
          resources=resources,
          node_selector=node_selector,
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
  config = XpkConfig()
  pod_image = config.get(KJOB_SHELL_IMAGE)
  if pod_image is None or len(pod_image) == 0:
    pod_image = PodTemplateDefaults.IMAGE.value

  return run_kubectl_apply(
      yml_string=pod_template_yaml.format(
          name=PodTemplateDefaults.NAME.value,
          container_name=PodTemplateDefaults.CONTAINER_NAME.value,
          image=pod_image,
          interactive_command=get_pod_template_interactive_command(),
      ),
      task="Creating PodTemplate",
      args=args,
  )


def prepare_kjob(args) -> int:
  xpk_print("Preparing kjob")

  system = get_cluster_system_characteristics(args)

  job_err_code = create_job_template_instance(args, system)
  if job_err_code > 0:
    return job_err_code

  pod_err_code = create_pod_template_instance(args)
  if pod_err_code > 0:
    return pod_err_code

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
  xpk_print("Creating kjob CRDs succeeded")
  return 0
