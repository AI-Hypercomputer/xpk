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

from ..utils import xpk_exit, xpk_print

JOB_TEMPLATE_PATH = "/../templates/slurm_job.yaml"
JOB_TEMPLATE_DEFAULT_NAME = "xpk-def-batch"
JOB_TEMPLATE_DEFAULT_PARALLELISM = 1
JOB_TEMPLATE_DEFAULT_COMPLETIONS = 1
JOB_TEMPLATE_DEFAULT_COMPLETION_MODE = "Indexed"
JOB_TEMPLATE_DEFAULT_CONT_NAME = "xpk-container"
JOB_TEMPLATE_DEFAULT_IMG = "ubuntu:22.04"
JOB_TEMPLATE_DEFAULT_RESTART_POLICY = "OnFailure"

XPK_SA = "xpk-sa"
STORAGE_CRD_PATH = "/../api/storage_crd.yaml"
STORAGE_TEMPLATE_PATH = "/../templates/storage.yaml"
STORAGE_CRD_NAME = "storages.xpk.x-k8s.io"
STORAGE_CRD_KIND = "Storage"
XPK_API_GROUP_NAME = "xpk.x-k8s.io"
XPK_API_GROUP_VERSION = "v1"


@dataclass
class JobTemplate:
  """
  Represents a JobTemplate resource in Kubernetes
  """


def create_job_template_instance(
    k8s_api_client: ApiClient, args: Namespace
) -> None:
  abs_path = f"{os.path.dirname(__file__)}{JOB_TEMPLATE_PATH}"
  with open(abs_path, "r", encoding="utf-8") as file:
    data = yaml.safe_load(file)

  data["metadata"]["name"] = JOB_TEMPLATE_DEFAULT_NAME
  spec = data["template"]["spec"]
  spec["parallelism"] = JOB_TEMPLATE_DEFAULT_PARALLELISM
  spec["completions"] = JOB_TEMPLATE_DEFAULT_COMPLETIONS
  spec["completionMode"] = JOB_TEMPLATE_DEFAULT_COMPLETION_MODE
  spec_template = spec["template"]["spec"]
  spec_template["containers"]["name"] = JOB_TEMPLATE_DEFAULT_CONT_NAME
  spec_template["containers"]["image"] = JOB_TEMPLATE_DEFAULT_IMG
  spec_template["restartPolicy"] = JOB_TEMPLATE_DEFAULT_RESTART_POLICY

  api_instance = k8s_client.CustomObjectsApi(k8s_api_client)
  xpk_print(f"Creating a new JobTemplate: {args.name}")
  try:
    api_instance.create_cluster_custom_object(
        group=XPK_API_GROUP_NAME, version=XPK_API_GROUP_VERSION, body=data
    )
  except ApiException as e:
    if e.status == 409:
      xpk_print(
          f"JobTemplate: {JOB_TEMPLATE_DEFAULT_NAME} already exists. Skipping"
          " its creation"
      )
    else:
      xpk_print(f"Encountered error during jobTemplate creation: {e}")
      xpk_exit(1)
