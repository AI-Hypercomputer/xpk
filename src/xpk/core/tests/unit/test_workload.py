"""
Copyright 2025 Google LLC

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

from xpk.core.workload import get_workload_list_gcp_link

TEST_PROJECT = 'test-project'
TEST_CLUSTER = 'test-cluster'
TEST_ZONE = 'us-central1-c'
LINK_WITHOUT_NAME_FILTER = 'https://console.cloud.google.com/kubernetes/workload/overview?project=test-project&pageState=(%22workload_list_table%22:(%22f%22:%22%255B%257B_22k_22_3A_22Cluster_22_2C_22t_22_3A10_2C_22v_22_3A_22_5C_22test-cluster_5C_22_22_2C_22i_22_3A_22metadata%252FclusterReference%252Fname_22%257D_2C%257B_22k_22_3A_22Location_22_2C_22t_22_3A10_2C_22v_22_3A_22_5C_22us-central1_5C_22_22_2C_22i_22_3A_22metadata%252FclusterReference%252FgcpLocation_22%257D_2C%257B_22k_22_3A_22Type_22_2C_22t_22_3A10_2C_22v_22_3A_22_5C_22Job_5C_22_22_2C_22i_22_3A_22type_meta%252FkindName_22%257D%255D%22))'
LINK_WITH_NAME_FILTER = 'https://console.cloud.google.com/kubernetes/workload/overview?project=test-project&pageState=(%22workload_list_table%22:(%22f%22:%22%255B%257B_22k_22_3A_22Cluster_22_2C_22t_22_3A10_2C_22v_22_3A_22_5C_22test-cluster_5C_22_22_2C_22i_22_3A_22metadata%252FclusterReference%252Fname_22%257D_2C%257B_22k_22_3A_22Location_22_2C_22t_22_3A10_2C_22v_22_3A_22_5C_22us-central1_5C_22_22_2C_22i_22_3A_22metadata%252FclusterReference%252FgcpLocation_22%257D_2C%257B_22k_22_3A_22Type_22_2C_22t_22_3A10_2C_22v_22_3A_22_5C_22Job_5C_22_22_2C_22i_22_3A_22type_meta%252FkindName_22%257D_2C%257B_22k_22_3A_22Name_22_2C_22t_22_3A10_2C_22v_22_3A_22_5C_22test-workload_5C_22_22_2C_22i_22_3A_22metadata%252Fname_22%257D%255D%22))'


def test_get_workload_list_gcp_link_without_job_name_filter():
  result = get_workload_list_gcp_link(
      project=TEST_PROJECT,
      cluster=TEST_CLUSTER,
      zone=TEST_ZONE,
      job_name_filter=None,
  )

  assert result == LINK_WITHOUT_NAME_FILTER


def test_get_workload_list_gcp_link_with_job_name_filter():
  result = get_workload_list_gcp_link(
      project=TEST_PROJECT,
      cluster=TEST_CLUSTER,
      zone=TEST_ZONE,
      job_name_filter='test-workload',
  )

  assert result == LINK_WITH_NAME_FILTER


def test_get_workload_list_gcp_link_with_invalid_job_name_filter():
  result = get_workload_list_gcp_link(
      project=TEST_PROJECT,
      cluster=TEST_CLUSTER,
      zone=TEST_ZONE,
      job_name_filter='test-workload.*',
  )

  assert result == LINK_WITHOUT_NAME_FILTER
