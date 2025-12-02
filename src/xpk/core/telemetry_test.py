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

import itertools
import pytest
import json
from .config import get_config, CLIENT_ID_KEY, SEND_TELEMETRY_KEY
from .telemetry import MetricsCollector, MetricsEventMetadataKey, should_send_telemetry
from ..utils.execution_context import set_dry_run
from ..utils.feature_flags import FeatureFlags
from pytest_mock import MockerFixture


@pytest.fixture(autouse=True)
def setup_mocks(mocker: MockerFixture):
  mocker.patch('xpk.core.telemetry._get_session_id', return_value='321231')
  mocker.patch('time.time', side_effect=itertools.count())
  mocker.patch('platform.python_version', return_value='99.99.99')
  mocker.patch('os.path.basename', return_value='xpk.py')
  mocker.patch('os.path.abspath', return_value='/home/xpk_user')
  set_dry_run(False)
  get_config().set(CLIENT_ID_KEY, 'client_id')
  yield
  get_config().set(CLIENT_ID_KEY, None)


@pytest.mark.parametrize(
    argnames='feature_flag,config_value,expected',
    argvalues=[
        (True, 'true', True),
        (False, 'true', False),
        (True, None, True),
        (True, 'false', False),
    ],
)
def test_should_send_telemetry_returns_correct_value(
    feature_flag: bool, config_value: str, expected: bool
):
  get_config().set(SEND_TELEMETRY_KEY, config_value)
  FeatureFlags.TELEMETRY_ENABLED = feature_flag
  assert should_send_telemetry() is expected


def test_metrics_collector_generates_client_id_if_not_present():
  get_config().set(CLIENT_ID_KEY, None)
  MetricsCollector.log_start(command='test')
  payload = json.loads(MetricsCollector.flush())
  extension_json = json.loads(payload['log_event'][0]['source_extension_json'])
  assert extension_json['client_install_id'] is not None
  assert len(extension_json['client_install_id']) > 0


def test_metrics_collector_logs_start_event_correctly():
  MetricsCollector.log_start(command='test')
  payload = json.loads(MetricsCollector.flush())
  extension_json = json.loads(payload['log_event'][0]['source_extension_json'])
  assert extension_json == {
      'client_install_id': 'client_id',
      'console_type': 'XPK',
      'event_metadata': [
          {'key': 'XPK_SESSION_ID', 'value': '321231'},
          {'key': 'XPK_DRY_RUN', 'value': 'false'},
          {'key': 'XPK_PYTHON_VERSION', 'value': '99.99.99'},
          {'key': 'XPK_RUNNING_AS_PIP', 'value': 'false'},
          {'key': 'XPK_RUNNING_FROM_SOURCE', 'value': 'true'},
          {'key': 'XPK_COMMAND', 'value': 'test'},
          {'key': 'XPK_LATENCY_SECONDS', 'value': '0'},
      ],
      'event_name': 'start',
      'event_type': 'commands',
      'release_version': 'v0.0.0',
  }


def test_metrics_collector_generates_client_id_when_not_present():
  get_config().set(CLIENT_ID_KEY, None)
  MetricsCollector.log_start(command='test')
  payload = json.loads(MetricsCollector.flush())
  extension_json = json.loads(payload['log_event'][0]['source_extension_json'])
  assert extension_json['client_install_id'] is not None
  assert len(extension_json['client_install_id']) > 0


def test_metrics_collector_logs_complete_event_correctly():
  MetricsCollector.log_complete(exit_code=2)
  payload = json.loads(MetricsCollector.flush())
  extension_json = json.loads(payload['log_event'][0]['source_extension_json'])
  assert extension_json == {
      'client_install_id': 'client_id',
      'console_type': 'XPK',
      'event_metadata': [
          {'key': 'XPK_SESSION_ID', 'value': '321231'},
          {'key': 'XPK_DRY_RUN', 'value': 'false'},
          {'key': 'XPK_PYTHON_VERSION', 'value': '99.99.99'},
          {'key': 'XPK_RUNNING_AS_PIP', 'value': 'false'},
          {'key': 'XPK_RUNNING_FROM_SOURCE', 'value': 'true'},
          {'key': 'XPK_EXIT_CODE', 'value': '2'},
          {'key': 'XPK_LATENCY_SECONDS', 'value': '0'},
      ],
      'event_name': 'complete',
      'event_type': 'commands',
      'release_version': 'v0.0.0',
  }


def test_metrics_collector_logs_custom_event_correctly():
  MetricsCollector.log_custom(
      name='test', metadata={MetricsEventMetadataKey.PROVISIONING_MODE: 'flex'}
  )
  payload = json.loads(MetricsCollector.flush())
  extension_json = json.loads(payload['log_event'][0]['source_extension_json'])
  assert extension_json == {
      'client_install_id': 'client_id',
      'console_type': 'XPK',
      'event_metadata': [
          {'key': 'XPK_SESSION_ID', 'value': '321231'},
          {'key': 'XPK_DRY_RUN', 'value': 'false'},
          {'key': 'XPK_PYTHON_VERSION', 'value': '99.99.99'},
          {'key': 'XPK_RUNNING_AS_PIP', 'value': 'false'},
          {'key': 'XPK_RUNNING_FROM_SOURCE', 'value': 'true'},
          {'key': 'XPK_PROVISIONING_MODE', 'value': 'flex'},
          {'key': 'XPK_LATENCY_SECONDS', 'value': '0'},
      ],
      'event_name': 'test',
      'event_type': 'custom',
      'release_version': 'v0.0.0',
  }


def test_metrics_collector_computest_latency_correctly():
  MetricsCollector.log_start(command='test')
  MetricsCollector.log_complete(exit_code=0)
  payload = json.loads(MetricsCollector.flush())
  extension_json = json.loads(payload['log_event'][1]['source_extension_json'])
  latency = (
      el['value']
      for el in extension_json['event_metadata']
      if el['key'] == 'XPK_LATENCY_SECONDS'
  )
  assert next(latency, None) == '1'


def test_metrics_collector_logs_correct_envelope():
  MetricsCollector.log_start(command='test')
  MetricsCollector.log_custom(
      name='test', metadata={MetricsEventMetadataKey.PROVISIONING_MODE: 'flex'}
  )
  MetricsCollector.log_complete(exit_code=2)
  payload = json.loads(MetricsCollector.flush())
  assert payload['client_info'] == {'client_type': 'XPK'}
  assert payload['log_source_name'] == 'CONCORD'
  assert payload['request_time_ms'] == 3000
  assert len(payload['log_event']) == 3


def test_metrics_collector_does_not_flush_event_twice():
  MetricsCollector.log_start(command='test')
  MetricsCollector.flush()
  MetricsCollector.log_start(command='version')
  payload = json.loads(MetricsCollector.flush())
  assert len(payload['log_event']) == 1


@pytest.mark.parametrize(
    argnames='dry_run,expected', argvalues=[(False, 'false'), (True, 'true')]
)
def test_metrics_collector_logs_correct_dry_run_value(
    dry_run: bool, expected: str
):
  set_dry_run(dry_run)
  MetricsCollector.log_start(command='test')
  payload = MetricsCollector.flush()
  assert _get_metadata_value(payload, 'XPK_DRY_RUN') == expected


@pytest.mark.parametrize(
    argnames='basename,expected',
    argvalues=[
        ('xpk', 'true'),
        ('xpk.py', 'false'),
    ],
)
def test_metrics_collectors_logs_correct_running_as_pip_value(
    basename: str, expected: str, mocker: MockerFixture
):
  mocker.patch('os.path.basename', return_value=basename)
  MetricsCollector.log_start(command='test')
  payload = MetricsCollector.flush()
  assert _get_metadata_value(payload, 'XPK_RUNNING_AS_PIP') == expected


@pytest.mark.parametrize(
    argnames='abspath,expected',
    argvalues=[
        ('/site-packages/', 'false'),
        ('/dist-packages/', 'false'),
        ('/home/xpk_user', 'true'),
    ],
)
def test_metrics_collectors_logs_correct_running_from_source_value(
    abspath: str, expected: str, mocker: MockerFixture
):
  mocker.patch('os.path.abspath', return_value=abspath)
  MetricsCollector.log_start(command='test')
  payload = MetricsCollector.flush()
  assert _get_metadata_value(payload, 'XPK_RUNNING_FROM_SOURCE') == expected


def _get_metadata_value(payload_str: str, key: str) -> str | None:
  payload = json.loads(payload_str)
  metadata = json.loads(payload['log_event'][0]['source_extension_json'])[
      'event_metadata'
  ]
  matching = (item['value'] for item in metadata if item['key'] == key)
  return next(matching, None)
