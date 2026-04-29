"""
Copyright 2026 Google LLC

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

import json

import pytest

from .quota_discovery import (
    TeamRouting,
    available_teams,
    available_value_classes,
    fetch_quota_config,
    max_k8s_workload_name_len,
    resolve_team,
    suggest,
)


def _sample_cfg() -> dict:
  return {
      'teams': {
          'ml-perf': {
              'namespace': 'poc-ml-perf',
              'localQueue': 'lq',
              'priorityClass': 'poc-ml-perf-priority',
          },
          'dev': {
              'namespace': 'poc-dev',
              'localQueue': 'lq',
              'priorityClass': 'poc-dev-priority',
          },
      },
      'valueClasses': ['benchmark', 'regression', 'development'],
      'sliceName': {'charLimit': 49, 'fixedOverhead': 26},
  }


# ---------- resolve_team ----------


def test_resolve_team_returns_dataclass_for_known_team():
  cfg = _sample_cfg()
  routing = resolve_team(cfg, 'ml-perf')
  assert isinstance(routing, TeamRouting)
  assert routing.namespace == 'poc-ml-perf'
  assert routing.local_queue == 'lq'
  assert routing.priority_class == 'poc-ml-perf-priority'


def test_resolve_team_raises_keyerror_for_unknown_team():
  cfg = _sample_cfg()
  with pytest.raises(KeyError) as exc_info:
    resolve_team(cfg, 'nonexistent')
  assert 'nonexistent' in str(exc_info.value)
  # Available teams should be listed for the user.
  assert 'ml-perf' in str(exc_info.value)
  assert 'dev' in str(exc_info.value)


def test_resolve_team_handles_empty_teams_map():
  cfg = {'teams': {}}
  with pytest.raises(KeyError) as exc_info:
    resolve_team(cfg, 'ml-perf')
  assert '<none>' in str(exc_info.value)


# ---------- available_teams / available_value_classes ----------


def test_available_teams_returns_sorted_keys():
  cfg = _sample_cfg()
  assert available_teams(cfg) == ['dev', 'ml-perf']


def test_available_teams_handles_missing_key():
  assert not available_teams({})


def test_available_value_classes_returns_list():
  cfg = _sample_cfg()
  assert available_value_classes(cfg) == ['benchmark', 'regression', 'development']


def test_available_value_classes_handles_missing_key():
  assert not available_value_classes({})


# ---------- max_k8s_workload_name_len ----------


def test_max_k8s_workload_name_len_uses_cfg_values():
  cfg = _sample_cfg()
  # 49 - 26 - len('poc-ml-perf') = 49 - 26 - 11 = 12
  assert max_k8s_workload_name_len(cfg, 'poc-ml-perf') == 12


def test_max_k8s_workload_name_len_falls_back_to_defaults():
  # No sliceName section present -> use defaults (49, 26)
  assert max_k8s_workload_name_len({}, 'poc-dev') == 49 - 26 - len('poc-dev')


def test_max_k8s_workload_name_len_handles_partial_overrides():
  cfg = {'sliceName': {'charLimit': 60}}  # fixedOverhead falls back to default 26
  assert max_k8s_workload_name_len(cfg, 'foo') == 60 - 26 - 3


# ---------- suggest ----------


def test_suggest_returns_close_matches_when_typo():
  candidates = ['ml-perf', 'dev', 'gsc', 'nightly']
  assert suggest('ml-pref', candidates) == ['ml-perf']


def test_suggest_returns_empty_for_no_match():
  candidates = ['ml-perf', 'dev']
  assert suggest('zzzzz', candidates) == []


def test_suggest_respects_limit():
  candidates = ['xa', 'xb', 'xc', 'xd', 'xe']
  assert len(suggest('x', candidates, limit=2)) <= 2


# ---------- fetch_quota_config (mocked) ----------


def test_fetch_quota_config_returns_parsed_payload(mocker):
  cfg = _sample_cfg()
  cm = {'data': {'config.json': json.dumps(cfg)}}
  mocker.patch(
      'xpk.core.quota_discovery.run_command_for_value',
      return_value=(0, json.dumps(cm)),
  )
  mocker.patch('xpk.core.quota_discovery.local_cache.current_context', return_value=None)
  out = fetch_quota_config()
  assert out == cfg


def test_fetch_quota_config_returns_none_if_kubectl_fails(mocker):
  mocker.patch(
      'xpk.core.quota_discovery.run_command_for_value',
      return_value=(1, ''),
  )
  assert fetch_quota_config() is None


def test_fetch_quota_config_returns_none_if_no_data_section(mocker):
  cm = {'kind': 'ConfigMap'}  # no 'data' key
  mocker.patch(
      'xpk.core.quota_discovery.run_command_for_value',
      return_value=(0, json.dumps(cm)),
  )
  assert fetch_quota_config() is None


def test_fetch_quota_config_returns_none_on_malformed_json(mocker):
  mocker.patch(
      'xpk.core.quota_discovery.run_command_for_value',
      return_value=(0, 'not-json'),
  )
  assert fetch_quota_config() is None


def test_fetch_quota_config_writes_cache_when_context_known(mocker):
  cfg = _sample_cfg()
  cm = {'data': {'config.json': json.dumps(cfg)}}
  mocker.patch(
      'xpk.core.quota_discovery.run_command_for_value',
      return_value=(0, json.dumps(cm)),
  )
  mocker.patch('xpk.core.quota_discovery.local_cache.current_context', return_value='gke_proj_zone_cluster')
  cache_write = mocker.patch('xpk.core.quota_discovery.local_cache.write')
  fetch_quota_config()
  cache_write.assert_called_once_with('gke_proj_zone_cluster', cfg)
