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

from ..core.network import get_subnetworks_for_a3mega, get_subnetworks_for_a3ultra
from ..core.capacity import H100_MEGA_DEVICE_TYPE, H200_DEVICE_TYPE
from ..utils.yaml import literal_string
from argparse import Namespace
import yaml
from .workload_decorators.tcpxo_decorator import decorate_job_template_with_a3mega
from .workload_decorators.rdma_decorator import decorate_job_template_with_a3ultra
import os
from ..utils.console import xpk_print, xpk_exit

from kubernetes import client as k8s_client
from kubernetes.client import ApiClient
from kubernetes.client.rest import ApiException
from .cluster import setup_k8s_env, XPK_SA, DEFAULT_NAMESPACE
from .storage import get_auto_mount_storages, get_auto_mount_gcsfuse_storages
from .commands import run_command_for_value, run_kubectl_apply, run_command_with_updates
from .config import XpkConfig, KJOB_SHELL_IMAGE, KJOB_SHELL_INTERACTIVE_COMMAND, KJOB_SHELL_WORKING_DIRECTORY, KJOB_BATCH_IMAGE, KJOB_BATCH_WORKING_DIRECTORY
from .resources import get_cluster_system_characteristics, SystemCharacteristics, AcceleratorType
from enum import Enum

KJOB_API_GROUP_NAME = "kjobctl.x-k8s.io"
KJOB_API_GROUP_VERSION = "v1alpha1"
KJOB_API_VOLUME_BUNDLE_PLURAL = "volumebundles"
VOLUME_BUNDLE_TEMPLATE_PATH = "/../templates/volume_bundle.yaml"


class AppProfileDefaults(Enum):
  NAME = "xpk-def-app-profile"


class JobTemplateDefaults(Enum):
  NAME = "xpk-def-batch"
  PARALLELISM = 1
  COMPLETIONS = 1
  CONTAINER_NAME = "xpk-batch-container"
  IMAGE = "ubuntu:22.04"
  WORKING_DIRECTORY = "/"


class PodTemplateDefaults(Enum):
  NAME = "xpk-def-pod"
  CONTAINER_NAME = "xpk-interactive-container"
  IMAGE = "busybox:1.28"
  WORKING_DIRECTORY = "/"
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
          dnsPolicy: ClusterFirstWithHostNet
          tolerations:
            - operator: "Exists"
              key: nvidia.com/gpu
          containers:
            - name: {container_name}
              image: {image}
              workingDir: {working_directory}
              {resources}
          {node_selector}
          restartPolicy: OnFailure
          serviceAccountName: {service_account}
"""
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
  volumeBundles: {volume_bundles}
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
        workingDir: {working_directory}
    initContainers:
      - name: init
        image: {image}
        command: ['/bin/mkdir', '-p', '{working_directory}']
    serviceAccountName: {service_account}
"""

Kueue_TAS_annotation = "kueue.x-k8s.io/podset-preferred-topology=cloud.google.com/gce-topology-host"


def get_a3ultra_pod_template_annotations(args: Namespace) -> list[str]:
  sub_networks = get_subnetworks_for_a3ultra(args.cluster)
  interfaces = [
      "[\n",
      '    {"interfaceName":"eth0","network":"default"},',
      *[
          f'    {{"interfaceName":"eth{i + 1}","network":"{sub_networks[i]}"}}{"," if i<8 else ""}'
          for i in range(9)
      ],
      "]",
  ]
  interfaces_joined = interfaces[0] + "\n".join(interfaces[1:])
  interfaces = (
      f"networking.gke.io/interfaces=$'{literal_string(interfaces_joined)}'"
  )
  return [
      "networking.gke.io/default-interface=eth0",
      interfaces,
  ]


def get_a3mega_pod_template_annotations(args: Namespace) -> list[str]:
  """Adds or updates annotations in the Pod template."""
  sub_networks = get_subnetworks_for_a3mega(args.cluster)
  interfaces = [
      "[\n",
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
      "- path: /dev/dmabuf_import_helper"
  )
  interfaces_joined = interfaces[0] + "\n".join(interfaces[1:])
  tcpxo = f"devices.gke.io/container.tcpxo-daemon=$'{joined}'"
  interfaces = (
      f"networking.gke.io/interfaces=$'{literal_string(interfaces_joined)}'"
  )
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


def create_app_profile_instance(
    args: Namespace, volume_bundles: list[str]
) -> int:
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
          volume_bundles=volume_bundles,
      ),
      task="Creating AppProfile",
      args=args,
  )


def decorate_job_template_with_gpu(yml_string: str, gpu_type: str) -> str:
  job_spec = yaml.safe_load(yml_string)["template"]
  if gpu_type == H100_MEGA_DEVICE_TYPE:
    job_spec = decorate_job_template_with_a3mega(job_spec)
  if gpu_type == H200_DEVICE_TYPE:
    job_spec = decorate_job_template_with_a3ultra(job_spec)
  job_template_dict = yaml.safe_load(yml_string)
  job_template_dict["template"] = job_spec
  return yaml.dump(job_template_dict, sort_keys=False)


def create_job_template_instance(
    args: Namespace,
    system: SystemCharacteristics | None,
    service_account: str,
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
      service_account=service_account,
  )
  if system is not None and system.accelerator_type == AcceleratorType["GPU"]:
    yml_string = decorate_job_template_with_gpu(yml_string, system.device_type)

  return run_kubectl_apply(
      yml_string,
      task="Creating JobTemplate",
      args=args,
  )


def create_pod_template_instance(args: Namespace, service_account: str) -> int:
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
  working_directory = config.get(KJOB_SHELL_WORKING_DIRECTORY)
  if working_directory is None or len(working_directory) == 0:
    working_directory = PodTemplateDefaults.WORKING_DIRECTORY.value

  return run_kubectl_apply(
      yml_string=pod_template_yaml.format(
          name=PodTemplateDefaults.NAME.value,
          container_name=PodTemplateDefaults.CONTAINER_NAME.value,
          image=pod_image,
          working_directory=working_directory,
          interactive_command=get_pod_template_interactive_command(),
          service_account=service_account,
      ),
      task="Creating PodTemplate",
      args=args,
  )


def prepare_kjob(args: Namespace) -> int:
  system = get_cluster_system_characteristics(args)

  k8s_api_client = setup_k8s_env(args)
  storages = get_auto_mount_storages(k8s_api_client)

  service_account = ""
  if len(storages) > 0:
    service_account = XPK_SA

  job_err_code = create_job_template_instance(args, system, service_account)
  if job_err_code > 0:
    return job_err_code

  pod_err_code = create_pod_template_instance(args, service_account)
  if pod_err_code > 0:
    return pod_err_code

  volume_bundles = [item.name for item in storages]

  return create_app_profile_instance(args, volume_bundles)


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


def create_volume_bundle_instance(
    k8s_api_client: ApiClient, args: Namespace
) -> None:
  """
  Creates a new VolumeBundle resource in the Kubernetes cluster.

  This function reads a VolumeBundle template from a YAML file, populates it with
  values from the provided arguments, and then creates the VolumeBundle object
  in the cluster.

  Args:
      k8s_api_client: An ApiClient object for interacting with the Kubernetes API.
      args: An argparse Namespace object containing the arguments for creating
            the Storage resource.
  """
  abs_path = f"{os.path.dirname(__file__)}{VOLUME_BUNDLE_TEMPLATE_PATH}"
  with open(abs_path, "r", encoding="utf-8") as file:
    data = yaml.safe_load(file)

  data["metadata"]["name"] = args.name
  spec = data["spec"]
  spec["volumes"] = []
  spec["containerVolumeMounts"] = []

  with open(args.manifest, "r", encoding="utf-8") as f:
    pv_pvc_definitions = yaml.safe_load_all(f)
    for obj in pv_pvc_definitions:
      if obj["kind"] == "PersistentVolumeClaim":
        spec["volumes"].append({
            "name": obj["metadata"]["name"],
            "persistentVolumeClaim": {
                "claimName": obj["metadata"]["name"],
                "readOnly": args.readonly,
            },
        })
        spec["containerVolumeMounts"].append({
            "name": obj["metadata"]["name"],
            "mountPath": args.mount_point,
        })

  data["spec"] = spec

  api_instance = k8s_client.CustomObjectsApi(k8s_api_client)
  try:
    api_instance.create_namespaced_custom_object(
        namespace=DEFAULT_NAMESPACE,
        group=KJOB_API_GROUP_NAME,
        version=KJOB_API_GROUP_VERSION,
        plural=KJOB_API_VOLUME_BUNDLE_PLURAL,
        body=data,
    )
    xpk_print(
        f"Created {KJOB_API_VOLUME_BUNDLE_PLURAL}.{KJOB_API_GROUP_NAME} object:"
        f" {data['metadata']['name']}"
    )
  except ApiException as e:
    if e.status == 409:
      xpk_print(
          f"VolumeBundle: {args.name} already exists. Skipping its creation"
      )
    else:
      xpk_print(f"Encountered error during VolumeBundle creation: {e}")
      xpk_exit(1)


def get_gcsfuse_annotation(args: Namespace) -> str | None:
  k8s_api_client = setup_k8s_env(args)
  gcsfuse_storages = get_auto_mount_gcsfuse_storages(k8s_api_client)
  if len(gcsfuse_storages) > 0:
    return "gke-gcsfuse/volumes=true"
  return None


def add_h100_mega_annotations(args, cmd: str) -> str:
  tcpxo, interfaces = get_a3mega_pod_template_annotations(args)
  cmd += f" --pod-template-annotation {tcpxo} \\\n"
  cmd += (
      ' --pod-template-annotation networking.gke.io/default-interface="eth0"'
      " \\\n"
  )
  cmd += f" --pod-template-annotation {interfaces} "
  return cmd


def add_h200_ultra_annotations(args, cmd) -> str:
  eth0, interfaces = get_a3ultra_pod_template_annotations(args)
  cmd += f" --pod-template-annotation {eth0} \\\n"
  cmd += f" --pod-template-annotation {interfaces} \\\n"
  return cmd


def get_gpu_type_from_cluster(args) -> str:
  system = get_cluster_system_characteristics(args)
  return system.device_type


def add_annotation_to_job(args, cmd: str) -> str:
  gpu_type = get_gpu_type_from_cluster(args)

  if gpu_type == H100_MEGA_DEVICE_TYPE:
    return add_h100_mega_annotations(args, cmd)
  if gpu_type == H200_DEVICE_TYPE:
    return add_h200_ultra_annotations(args, cmd)
  return cmd
