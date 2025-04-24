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

from ..utils.console import xpk_exit, xpk_print
from ..utils import templates
from ..utils.kubectl import apply_kubectl_manifest
from ..core.cluster import setup_k8s_env

MTC_CPC_PATH = "/../templates/mtc-cpc.yaml"


def create_mtc_cpc(
    mtc_gcs_bucket: str,
    mtc_machine_type: str,
    mtc_toleration_key: str,
    mtc_ramdisk_size: str,
) -> dict:
  data = templates.load(MTC_CPC_PATH)

  data["spec"]["cloudStorageBucketName"] = mtc_gcs_bucket
  data["spec"]["nodeSelector"][
      "node.kubernetes.io/instance-type"
  ] = mtc_machine_type
  data["spec"]["tolerations"][0]["key"] = mtc_toleration_key
  data["spec"]["inMemoryVolumeSize"] = mtc_ramdisk_size

  return data


def install_mtc_on_cluster(args, system) -> int:
  """Install MTC on the cluster

  Args:
    args: user provided arguments for running the command.

  Returns:
    return code of the command.
  """
  if args.mtc_gcs_bucket is None:
    xpk_print("MTC GCS bucket is required.")
    xpk_exit(1)
  if args.mtc_gcs_bucket.startswith("gs://"):
    args.mtc_gcs_bucket = args.mtc_gcs_bucket.replace("gs://", "")

  if args.mtc_ramdisk_size is None:
    xpk_print("MTC ramdisk size is required.")
    xpk_exit(1)

  if args.mtc_toleration_key is None:
    args.mtc_toleration_key = "google.com/tpu"

  mtc_checkpoint_configuration_crd_data = create_mtc_cpc(
      args.mtc_gcs_bucket,
      system.gce_machine_type,
      args.mtc_toleration_key,
      args.mtc_ramdisk_size,
  )
  xpk_print("Applying MTC Checkpoint Configuration")
  k8s_api_client = setup_k8s_env(args)
  return_code = apply_kubectl_manifest(
      k8s_api_client, [mtc_checkpoint_configuration_crd_data]
  )

  return return_code
