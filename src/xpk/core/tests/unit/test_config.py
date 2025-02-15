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

from xpk.core.config import XpkConfig, CFG_BUCKET_KEY, CLUSTER_NAME_KEY, PROJECT_KEY, ZONE_KEY

import os
import pytest

config_tmp_path = '/tmp/config/config.yaml'


@pytest.fixture(name='_')
def _():
  if os.path.exists(config_tmp_path):
    os.remove(config_tmp_path)
  yield
  if os.path.exists(config_tmp_path):
    os.remove(config_tmp_path)


def test_config(_):
  cfg = XpkConfig(config_tmp_path)
  cfg.set('project-id', 'foo')
  project_id = cfg.get('project-id')
  assert project_id == 'foo'


def test_config_get_all(_):
  cfg = XpkConfig(config_tmp_path)
  cfg.set(PROJECT_KEY, 'foo')
  cfg.set(CLUSTER_NAME_KEY, 'bar')
  cfg.set(ZONE_KEY, 'europe-west1-a')
  cfg.set(CFG_BUCKET_KEY, 'cfg-bucket')

  cfg_all = cfg.get_all()
  assert cfg_all[PROJECT_KEY] == 'foo'
  assert cfg_all[CLUSTER_NAME_KEY] == 'bar'
  assert cfg_all[ZONE_KEY] == 'europe-west1-a'
  assert cfg_all[CFG_BUCKET_KEY] == 'cfg-bucket'


def test_config_get_empty(_):
  cfg = XpkConfig(config_tmp_path)
  val = cfg.get(PROJECT_KEY)
  assert val is None


def test_config_get_all_empty(_):
  cfg = XpkConfig(config_tmp_path)
  val = cfg.get_all()
  assert not val


def test_config_set_incorrect(_):
  cfg = XpkConfig(config_tmp_path)
  cfg.set('foo', 'bar')
  cfg_all = cfg.get_all()
  assert not cfg_all
