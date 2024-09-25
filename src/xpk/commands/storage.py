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

from kubernetes import client as k8s_client
from kubernetes.client.exceptions import ApiException

from ..core.core import (
    setup_k8s_env,
    update_cluster_with_gcsfuse_driver_if_necessary,
    update_cluster_with_workload_identity_if_necessary,
)
from ..core.storage import (
    STORAGE_CRD_KIND,
    XPK_API_GROUP_NAME,
    XPK_API_GROUP_VERSION,
    create_storage_instance,
    get_storage,
    install_storage_crd,
    list_storages,
    print_storages_for_cluster,
)
from ..utils import apply_kubectl_manifest, xpk_exit, xpk_print


def storage_create(args: Namespace) -> None:
  k8s_api_client = setup_k8s_env(args)

  install_storage_crd(k8s_api_client)
  return_code = update_cluster_with_workload_identity_if_necessary(args)
  if return_code > 0:
    xpk_exit(return_code)
  return_code = update_cluster_with_gcsfuse_driver_if_necessary(args)
  if return_code > 0:
    xpk_exit(return_code)

  create_storage_instance(k8s_api_client, args)
  apply_kubectl_manifest(k8s_api_client, args.manifest)


def storage_list(args: Namespace) -> None:
  k8s_api_client = setup_k8s_env(args)
  install_storage_crd(k8s_api_client)
  storages = list_storages(k8s_api_client)
  print_storages_for_cluster(storages, args.cluster)


def storage_delete(args: Namespace) -> None:
  k8s_api_client = setup_k8s_env(args)
  install_storage_crd(k8s_api_client)
  api_instance = k8s_client.CustomObjectsApi(k8s_api_client)
  core_api = k8s_client.CoreV1Api()
  try:
    storage = get_storage(k8s_api_client, args.name)
    core_api.delete_namespaced_persistent_volume_claim(storage.pvc, "default")
    core_api.delete_persistent_volume(storage.pv)

    api_instance.delete_cluster_custom_object(
        name=args.name,
        group=XPK_API_GROUP_NAME,
        version=XPK_API_GROUP_VERSION,
        plural=STORAGE_CRD_KIND.lower() + "s",
    )
  except ApiException as e:
    if e.status == 404:
      xpk_print(f"Storage: {args.name} not found. Might be already deleted.")
    else:
      xpk_print(f"Encountered error during storage deletion: {e}")
      xpk_exit(1)
