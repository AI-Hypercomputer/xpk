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

from unittest.mock import MagicMock
import pytest
from xpk.core.mtc import add_mtc_bucket_iam_member, create_mtc_cpc
from argparse import Namespace


def test_add_mtc_bucket_iam_member(mocker):
  mock_client_class = mocker.patch("xpk.core.mtc.gcp_storage.Client")
  mock_client = mock_client_class.return_value
  mock_bucket = mock_client.bucket.return_value
  mock_policy = MagicMock()
  mock_policy.bindings = []
  mock_bucket.get_iam_policy.return_value = mock_policy

  args = Namespace(
      mtc_gcs_bucket="my-test-bucket",
      project_number="1234567890",
      project="my-project",
  )

  add_mtc_bucket_iam_member(args)

  mock_client.bucket.assert_called_once_with("my-test-bucket")
  mock_bucket.get_iam_policy.assert_called_once_with(requested_policy_version=3)

  expected_member = "principal://iam.googleapis.com/projects/1234567890/locations/global/workloadIdentityPools/my-project.svc.id.goog/subject/ns/gke-managed-checkpointing/sa/gke-checkpointing-multitier-node"

  assert len(mock_policy.bindings) == 1
  assert mock_policy.bindings[0]["role"] == "roles/storage.objectUser"
  assert expected_member in mock_policy.bindings[0]["members"]

  mock_bucket.set_iam_policy.assert_called_once_with(mock_policy)


def test_create_mtc_cpc(mocker):
  # Mock templates.load to return a minimal valid dictionary structure to avoid depending on actual file content
  mock_load = mocker.patch("xpk.core.mtc.templates.load")
  mock_load.return_value = {
      "spec": {
          "cloudStorageBucketName": "",
          "nodeSelector": {"node.kubernetes.io/instance-type": ""},
          "tolerations": [{"key": ""}],
          "inMemoryVolumeSize": "",
      }
  }

  result = create_mtc_cpc(
      mtc_gcs_bucket="my-bucket",
      mtc_machine_type="ct4p-hightpu-4t",
      mtc_toleration_key="my-key",
      mtc_ramdisk_size="100Gi",
  )

  assert result["spec"]["cloudStorageBucketName"] == "my-bucket"
  assert (
      result["spec"]["nodeSelector"]["node.kubernetes.io/instance-type"]
      == "ct4p-hightpu-4t"
  )
  assert result["spec"]["tolerations"][0]["key"] == "my-key"
  assert result["spec"]["inMemoryVolumeSize"] == "100Gi"
