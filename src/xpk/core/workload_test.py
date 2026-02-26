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

from unittest.mock import MagicMock
import pytest
import re
from pytest_mock import MockerFixture
from xpk.core.testing.commands_tester import CommandsTester
from xpk.core.workload import get_jobsets_list_gcp_link, get_workload_list


def _parse_workload_table(table_str: str) -> list[dict[str, str]]:
  if not table_str:
    return []
  lines = table_str.strip().split('\n')
  if not lines:
    return []
  headers = [h.strip() for h in re.split(r' {3,}', lines[0].strip())]
  result = []
  for line in lines[1:]:
    row_values = [v.strip() for v in re.split(r' {3,}', line.strip())]
    row_dict = dict(zip(headers, row_values))
    result.append(row_dict)
  return result


@pytest.fixture(autouse=True)
def commands_tester(mocker: MockerFixture) -> CommandsTester:
  return CommandsTester(mocker)


def test_get_jobsets_list_gcp_link():
  result = get_jobsets_list_gcp_link(
      project='test-project',
  )

  assert (
      result
      == 'https://console.cloud.google.com/kubernetes/aiml/deployments/jobs?project=test-project'
  )


def test_get_workload_list(commands_tester: CommandsTester):
  mock_output = (
      'job-test~2024-01-01T00:00:00Z~high~32~32~0~Running~All'
      ' good~2024-01-01T00:01:00Z'
  )
  commands_tester.set_result_for_command(
      (0, mock_output), 'kubectl', 'get', 'workloads'
  )
  args = MagicMock()
  args.filter_by_status = 'EVERYTHING'
  args.filter_by_job = None

  return_code, return_value = get_workload_list(args)

  assert return_code == 0
  parsed_table = _parse_workload_table(return_value)
  assert len(parsed_table) == 1
  assert parsed_table[0]['Jobset Name'] == 'job-test'
  assert parsed_table[0]['Status'] == 'Running'
  assert parsed_table[0]['TPU VMs Needed'] == '32'
  assert parsed_table[0]['TPU VMs Running/Ran'] == '32'
  assert parsed_table[0]['TPU VMs Done'] == '0'
  assert parsed_table[0]['Status Message'] == 'All good'
  assert parsed_table[0]['Created Time'] == '2024-01-01T00:00:00Z'
  assert parsed_table[0]['Status Time'] == '2024-01-01T00:01:00Z'
  assert parsed_table[0]['Priority'] == 'high'


def test_get_workload_list_super_slicing(commands_tester: CommandsTester):
  mock_output = (
      'job-super~2024-01-01T00:00:00Z~high~32 32~32 32~0 0~Running~All'
      ' good~2024-01-01T00:01:00Z\njob-normal~2024-01-02T00:00:00Z~low~4~4~0~Running~All'
      ' good~2024-01-02T00:01:00Z\njob-pending~2024-01-03T00:00:00Z~high~16~~0~Admitted~Waiting~2024-01-03T00:01:00Z'
  )
  commands_tester.set_result_for_command(
      (0, mock_output), 'kubectl', 'get', 'workloads'
  )
  args = MagicMock()
  args.filter_by_status = 'EVERYTHING'
  args.filter_by_job = None

  return_code, return_value = get_workload_list(args)

  assert return_code == 0
  parsed_table = _parse_workload_table(return_value)
  assert len(parsed_table) == 3

  assert parsed_table[0]['Jobset Name'] == 'job-super'
  assert parsed_table[0]['TPU VMs Needed'] == '64'  # 32 + 32 Needed
  assert parsed_table[0]['TPU VMs Running/Ran'] == '64'  # 32 + 32 Running
  assert parsed_table[0]['TPU VMs Done'] == '0'  # 0 + 0 Done
  assert parsed_table[0]['Status'] == 'Running'

  assert parsed_table[1]['Jobset Name'] == 'job-normal'
  assert parsed_table[1]['TPU VMs Needed'] == '4'
  assert parsed_table[1]['TPU VMs Running/Ran'] == '4'
  assert parsed_table[1]['TPU VMs Done'] == '0'
  assert parsed_table[1]['Status'] == 'Running'

  assert parsed_table[2]['Jobset Name'] == 'job-pending'
  assert parsed_table[2]['TPU VMs Needed'] == '16'
  assert parsed_table[2]['TPU VMs Running/Ran'] == '<none>'
  assert parsed_table[2]['TPU VMs Done'] == '0'
  assert parsed_table[2]['Status'] == 'Admitted'
