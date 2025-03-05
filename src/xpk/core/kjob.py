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

from ..utils.yaml import literal_string
from argparse import Namespace
import yaml
from .workload_decorators.tcpxo_decorator import decorate_kjob_job
from ..utils.console import xpk_print
from .commands import run_command_for_value, run_kubectl_apply, run_command_with_updates
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
        command: [{interactive_command}]
"""


def get_pod_template_annotations(args: Namespace) -> list[str]:
  """Adds or updates annotations in the Pod template."""
  sub_networks = [f"{args.cluster}-gpunet-{i}-subnet" for i in range(8)]
  interfaces = [
      "[",
      '    {"interfaceName":"eth0","network":"default"},',
      *[
          f'    {{"interfaceName":"eth{i + 1}","network":"{sub_networks[i]}"}}{"," if i<7 else ""}'
          for i in range(8)
      ],
      "]",
  ]
  joined = (
      "- path: /dev/nvidia0\n"
      "- path: /dev/nvidia1\n"
      "- path: /dev/nvidia2\n"
      "- path: /dev/nvidia3\n"
      "- path: /dev/nvidia4\n"
      "- path: /dev/nvidia5\n"
      "- path: /dev/nvidia6\n"
      "- path: /dev/nvidia7\n"
      "- path: /dev/nvidiactl\n"
      "- path: /dev/nvidia-uvm\n"
      "- path: /dev/dmabuf_import_helper\n"
  )
  interfaces_joined = interfaces[0]+"\n".join(interfaces[1:])
  tcpxo = f"devices.gke.io/container.tcpxo-daemon=$'{joined}'"
  # annotations.append(
  #     "networking.gke.io/default-interface=\"eth0\"",
  # )
  interfaces = f"networking.gke.io/interfaces=$'{literal_string(interfaces_joined)}'"
  return tcpxo, interfaces

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
<<<<<<< Updated upstream
  return run_kubectl_apply(
      yml_string=job_template_yaml.format(
          name=JobTemplateDefaults.NAME.value,
          parallelism=JobTemplateDefaults.PARALLELISM.value,
          completions=JobTemplateDefaults.COMPLETIONS.value,
          container_name=JobTemplateDefaults.CONTAINER_NAME.value,
          image=JobTemplateDefaults.IMAGE.value,
      ),
=======
  config = XpkConfig()
  job_image = config.get(KJOB_BATCH_IMAGE)
  if job_image is None or len(job_image) == 0:
    job_image = JobTemplateDefaults.IMAGE.value
  working_directory = config.get(KJOB_BATCH_WORKING_DIRECTORY)
  if working_directory is None or len(working_directory) == 0:
    working_directory = JobTemplateDefaults.WORKING_DIRECTORY.value

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
  yml_string = job_template_yaml.format(
      name=JobTemplateDefaults.NAME.value,
      parallelism=JobTemplateDefaults.PARALLELISM.value,
      completions=JobTemplateDefaults.COMPLETIONS.value,
      container_name=JobTemplateDefaults.CONTAINER_NAME.value,
      image=job_image,
      working_directory=working_directory,
      resources=resources,
      node_selector=node_selector,
  )
  job_spec = yaml.safe_load(yml_string)["template"]
  job_spec = decorate_kjob_job(job_spec)
  job_template_dict = yaml.safe_load(yml_string)
  job_template_dict["template"] = job_spec
  return run_kubectl_apply(
      yaml.dump(job_template_dict, sort_keys=False),
>>>>>>> Stashed changes
      task="Creating JobTemplate",
      args=args,
  )


<<<<<<< Updated upstream
=======
# this may be moved to shell command
>>>>>>> Stashed changes
def create_pod_template_instance(args: Namespace) -> int:
  """Create new PodTemplate instance on cluster with default settings.

  Args:
    args - user provided arguments
  Returns:
    exit_code > 0 if creating PodTemplate fails, 0 otherwise
  """
<<<<<<< Updated upstream
=======
  config = XpkConfig()
  pod_image = config.get(KJOB_SHELL_IMAGE)
  if pod_image is None or len(pod_image) == 0:
    pod_image = PodTemplateDefaults.IMAGE.value
  working_directory = config.get(KJOB_SHELL_WORKING_DIRECTORY)
  xpk_print("working directory is: ", working_directory)
  if working_directory is None or len(working_directory) == 0:
    working_directory = PodTemplateDefaults.WORKING_DIRECTORY.value

>>>>>>> Stashed changes
  return run_kubectl_apply(
      yml_string=pod_template_yaml.format(
          name=PodTemplateDefaults.NAME.value,
          container_name=PodTemplateDefaults.CONTAINER_NAME.value,
          image=PodTemplateDefaults.IMAGE.value,
          interactive_command=PodTemplateDefaults.INTERACTIVE_COMMAND.value,
      ),
      task="Creating PodTemplate",
      args=args,
  )


def prepare_kjob(args) -> int:
<<<<<<< Updated upstream
  job_err_code = create_job_template_instance(args)
=======
  xpk_print("Preparing kjob")
  system = get_cluster_system_characteristics(args)
  job_err_code = create_job_template_instance(args, system)
>>>>>>> Stashed changes
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
