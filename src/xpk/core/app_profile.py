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

import os
from argparse import Namespace
from dataclasses import dataclass

import yaml
from kubernetes import client as k8s_client
from kubernetes import utils
from kubernetes.client import ApiClient
from kubernetes.client.exceptions import ApiException
from kubernetes.client.models.v1_persistent_volume import V1PersistentVolume
from kubernetes.utils import FailToCreateError
from tabulate import tabulate
from argparse import Namespace
from ..utils import xpk_exit, xpk_print

from .job_template import JOB_TEMPLATE_DEFAULT_NAME

APP_PROFILE_TEMPLATE_PATH = "/../templates/slurm_job.yaml"
APP_PROFILE_TEMPLATE_DEFAULT_NAME = "xpk-def-app-profile"
APP_PROFILE_TEMPLATE_DEFAULT_PARALLELISM = 1
APP_PROFILE_TEMPLATE_DEFAULT_COMPLETIONS = 1
APP_PROFILE_TEMPLATE_DEFAULT_COMPLETION_MODE = "Indexed"
APP_PROFILE_TEMPLATE_DEFAULT_CONT_NAME = "xpk-container"
APP_PROFILE_TEMPLATE_DEFAULT_IMG = "ubuntu:22.04"
APP_PROFILE_TEMPLATE_DEFAULT_RESTART_POLICY = "OnFailure"
APP_PROFILE_TEMPLATE_MODE_NAME = "Slurm"
APP_PROFILE_TEMPLATE_NAMESPACE = "default"
XPK_SA = "xpk-sa"
STORAGE_CRD_PATH = "/../api/storage_crd.yaml"
STORAGE_TEMPLATE_PATH = "/../templates/storage.yaml"
STORAGE_CRD_NAME = "storages.xpk.x-k8s.io"
STORAGE_CRD_KIND = "Storage"
XPK_API_GROUP_NAME = "xpk.x-k8s.io"
XPK_API_GROUP_VERSION = "v1"


@dataclass
class AppProfile:
  """
  Represents a AppProfile resource in Kubernetes
  """


app_profile_yaml = """
apiVersion: kjobctl.x-k8s.io/v1alpha1
kind: ApplicationProfile
metadata:
  name: slurm-profile
  namespace: default
spec:
  supportedModes:
    - name: Slurm
      template: sample-slurm-template
      requiredFlags: []
"""


def create_app_profile_instance(
    k8s_api_client: ApiClient, args: Namespace
) -> None:
  yml_string = app_profile_yaml.format(
      name=JOB_TEMPLATE_DEFAULT_NAME,
      parallelism=JOB_TEMPLATE_DEFAULT_PARALLELISM,
      completions=JOB_TEMPLATE_DEFAULT_COMPLETIONS,
      container=JOB_TEMPLATE_DEFAULT_CONT_NAME,
      image=JOB_TEMPLATE_DEFAULT_IMG,
  )
  print(yml_string)
  tmp = write_tmp_file(yml_string)
  command = f"kubectl apply -f {str(tmp.file.name)}"
  return_code = run_command_with_updates(command, "Creating JobTemplate", args)
  if return_code != 0:
    xpk_exit(return_code)
