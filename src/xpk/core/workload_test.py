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
import json
from pytest_mock import MockerFixture
from xpk.core.testing.commands_tester import CommandsTester
from xpk.core.workload import get_jobsets_list_gcp_link, get_workload_list


from dataclasses import dataclass


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


@dataclass
class _MockWorkloadData:
  jobset_name: str
  created_time: str
  priority: str
  needed: int | str
  running: int | str
  done: int | str
  status: str
  message: str
  status_time: str


def _create_mock_workload_json(data: _MockWorkloadData):
  return {
      'metadata': {
          'creationTimestamp': data.created_time,
          'ownerReferences': [{'name': data.jobset_name}],
      },
      'spec': {
          'podSets': [{
              'count': data.needed,
              'template': {'spec': {'priorityClassName': data.priority}},
          }]
      },
      'status': {
          'admission': {'podSetAssignments': [{'count': data.running}]},
          'reclaimablePods': [{'count': data.done}],
          'conditions': [{
              'type': data.status,
              'message': data.message,
              'lastTransitionTime': data.status_time,
          }],
      },
  }


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
  mock_output = json.dumps({
      'items': [
          _create_mock_workload_json(
              _MockWorkloadData(
                  jobset_name='job-test',
                  created_time='2024-01-01T00:00:00Z',
                  priority='high',
                  needed=32,
                  running=32,
                  done=0,
                  status='Running',
                  message='All good',
                  status_time='2024-01-01T00:01:00Z',
              )
          )
      ]
  })
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
  assert parsed_table[0]['Status'] == 'Unknown'
  assert parsed_table[0]['TPU VMs Needed'] == '32'
  assert parsed_table[0]['TPU VMs Running/Ran'] == '32'
  assert parsed_table[0]['TPU VMs Done'] == '0'
  assert parsed_table[0]['Status Message'] == 'All good'
  assert parsed_table[0]['Created Time'] == '2024-01-01T00:00:00Z'
  assert parsed_table[0]['Status Time'] == '2024-01-01T00:01:00Z'
  assert parsed_table[0]['Priority'] == 'high'


def test_get_workload_list_filter_by_job(commands_tester: CommandsTester):
  mock_output = json.dumps({
      'items': [
          _create_mock_workload_json(
              _MockWorkloadData(
                  jobset_name='job-test-1',
                  created_time='2024-01-01T00:00:00Z',
                  priority='high',
                  needed=32,
                  running=32,
                  done=0,
                  status='Running',
                  message='All good',
                  status_time='2024-01-01T00:01:00Z',
              )
          ),
          _create_mock_workload_json(
              _MockWorkloadData(
                  jobset_name='job-test-2',
                  created_time='2024-01-02T00:00:00Z',
                  priority='low',
                  needed=4,
                  running=4,
                  done=0,
                  status='Running',
                  message='All good',
                  status_time='2024-01-02T00:01:00Z',
              )
          ),
          _create_mock_workload_json(
              _MockWorkloadData(
                  jobset_name='other-job',
                  created_time='2024-01-03T00:00:00Z',
                  priority='high',
                  needed=16,
                  running='',
                  done=0,
                  status='Admitted',
                  message='Waiting',
                  status_time='2024-01-03T00:01:00Z',
              )
          ),
      ]
  })
  commands_tester.set_result_for_command(
      (0, mock_output), 'kubectl', 'get', 'workloads'
  )
  args = MagicMock()
  args.filter_by_status = 'EVERYTHING'
  args.filter_by_job = 'job-test'

  return_code, return_value = get_workload_list(args)

  assert return_code == 0
  parsed_table = _parse_workload_table(return_value)
  assert len(parsed_table) == 2
  assert parsed_table[0]['Jobset Name'] == 'job-test-1'
  assert parsed_table[1]['Jobset Name'] == 'job-test-2'


@pytest.mark.parametrize(
    'filter_by_status, expected_job_names',
    [
        (
            'EVERYTHING',
            [
                'queued-job',
                'running-job',
                'success-job',
                'failed-job',
            ],
        ),
        ('QUEUED', ['queued-job']),
        ('RUNNING', ['running-job']),
        ('FINISHED', ['success-job', 'failed-job']),
        ('SUCCESSFUL', ['success-job']),
        ('FAILED', ['failed-job']),
    ],
)
def test_get_workload_list_filters(
    commands_tester: CommandsTester,
    filter_by_status: str,
    expected_job_names: list[str],
):
  mock_output = json.dumps({
      'items': [
          _create_mock_workload_json(
              _MockWorkloadData(
                  jobset_name='queued-job',
                  created_time='2024-01-01T00:00:00Z',
                  priority='high',
                  needed=4,
                  running='',
                  done=0,
                  status='Admitted',
                  message='Waiting',
                  status_time='2024-01-01T00:01:00Z',
              )
          ),
          _create_mock_workload_json(
              _MockWorkloadData(
                  jobset_name='running-job',
                  created_time='2024-01-01T00:00:00Z',
                  priority='high',
                  needed=4,
                  running=4,
                  done=0,
                  status='Admitted',
                  message='Running',
                  status_time='2024-01-01T00:01:00Z',
              )
          ),
          _create_mock_workload_json(
              _MockWorkloadData(
                  jobset_name='success-job',
                  created_time='2024-01-01T00:00:00Z',
                  priority='high',
                  needed=4,
                  running=4,
                  done=4,
                  status='Finished',
                  message='Job finishedsuccessfully',
                  status_time='2024-01-01T00:01:00Z',
              )
          ),
          _create_mock_workload_json(
              _MockWorkloadData(
                  jobset_name='failed-job',
                  created_time='2024-01-01T00:00:00Z',
                  priority='high',
                  needed=4,
                  running=4,
                  done=0,
                  status='Finished',
                  message='Job failed witherror',
                  status_time='2024-01-01T00:01:00Z',
              )
          ),
      ]
  })
  commands_tester.set_result_for_command(
      (0, mock_output), 'kubectl', 'get', 'workloads'
  )
  args = MagicMock()
  args.filter_by_status = filter_by_status
  args.filter_by_job = None

  return_code, return_value = get_workload_list(args)

  assert return_code == 0
  parsed_table = _parse_workload_table(return_value)
  actual_job_names = [row['Jobset Name'] for row in parsed_table]
  assert actual_job_names == expected_job_names
