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

import pytest
from pytest_mock import MockerFixture
from xpk.core.mtc import add_mtc_bucket_iam_member, create_mtc_cpc
from argparse import Namespace
from .testing.commands_tester import CommandsTester


@pytest.fixture(autouse=True)
def commands_tester(mocker: MockerFixture) -> CommandsTester:
  return CommandsTester(mocker)


def test_add_mtc_bucket_iam_member(commands_tester: CommandsTester):
  args = Namespace(
      mtc_gcs_bucket="my-test-bucket",
      project_number="1234567890",
      project="my-project",
  )

  commands_tester.set_result_for_command(
      (0, ""), "gcloud storage buckets add-iam-policy-binding"
  )

  add_mtc_bucket_iam_member(args)

  expected_member = "principal://iam.googleapis.com/projects/1234567890/locations/global/workloadIdentityPools/my-project.svc.id.goog/subject/ns/gke-managed-checkpointing/sa/gke-checkpointing-multitier-node"
  commands_tester.assert_command_run(
      "gcloud storage buckets add-iam-policy-binding gs://my-test-bucket"
      f" --member='{expected_member}'"
      " --role='roles/storage.objectUser'"
      " --project=my-project --quiet"
  )


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
