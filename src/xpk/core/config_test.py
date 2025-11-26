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

from xpk.core.config import FileSystemConfig, InMemoryXpkConfig, CFG_BUCKET_KEY, CLUSTER_NAME_KEY, PROJECT_KEY, ZONE_KEY, _get_version
from unittest.mock import patch
from importlib.metadata import PackageNotFoundError

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


@patch('os.getenv', return_value='10.0.0')
def test_get_version_returns_overriden_value_when_it_is_overriden(_):
  assert _get_version() == '10.0.0'


@patch('os.getenv', return_value='')
@patch('xpk.core.config.setuptools_get_version', return_value='10.0.0')
def test_get_version_returns_value_from_setuptools_scm_when_there_is_no_override(
    *_,
):
  assert _get_version() == '10.0.0'


@patch('os.getenv', return_value='')
@patch(
    'xpk.core.config.setuptools_get_version',
    side_effect=LookupError('unable to find git version'),
)
@patch('xpk.core.config.version', return_value='10.0.0')
def test_get_version_returns_value_from_pip_when_there_is_no_setuptools_could_be_resolved(
    *_,
):
  assert _get_version() == '10.0.0'


@patch('os.getenv', return_value='')
@patch(
    'xpk.core.config.setuptools_get_version',
    side_effect=LookupError('unable to find git version'),
)
@patch(
    'xpk.core.config.version',
    side_effect=PackageNotFoundError('unable to locate package'),
)
def test_get_version_returns_none_when_no_version_could_be_resolved(*_):
  with pytest.raises(LookupError):
    _get_version()


@pytest.mark.parametrize(
    argnames='cfg',
    argvalues=[(FileSystemConfig(config_tmp_path)), (InMemoryXpkConfig())],
)
def test_config(_, cfg):
  cfg.set('project-id', 'foo')
  project_id = cfg.get('project-id')
  assert project_id == 'foo'


@pytest.mark.parametrize(
    argnames='cfg',
    argvalues=[(FileSystemConfig(config_tmp_path)), (InMemoryXpkConfig())],
)
def test_config_get_all(_, cfg):
  cfg.set(PROJECT_KEY, 'foo')
  cfg.set(CLUSTER_NAME_KEY, 'bar')
  cfg.set(ZONE_KEY, 'europe-west1-a')
  cfg.set(CFG_BUCKET_KEY, 'cfg-bucket')

  cfg_all = cfg.get_all()
  assert cfg_all[PROJECT_KEY] == 'foo'
  assert cfg_all[CLUSTER_NAME_KEY] == 'bar'
  assert cfg_all[ZONE_KEY] == 'europe-west1-a'
  assert cfg_all[CFG_BUCKET_KEY] == 'cfg-bucket'


@pytest.mark.parametrize(
    argnames='cfg',
    argvalues=[(FileSystemConfig(config_tmp_path)), (InMemoryXpkConfig())],
)
def test_config_get_empty(_, cfg):
  val = cfg.get(PROJECT_KEY)
  assert val is None


@pytest.mark.parametrize(
    argnames='cfg',
    argvalues=[(FileSystemConfig(config_tmp_path)), (InMemoryXpkConfig())],
)
def test_config_get_all_empty(_, cfg):
  val = cfg.get_all()
  assert not val


@pytest.mark.parametrize(
    argnames='cfg',
    argvalues=[(FileSystemConfig(config_tmp_path)), (InMemoryXpkConfig())],
)
def test_config_set_incorrect(cfg, _):
  cfg.set('foo', 'bar')
  cfg_all = cfg.get_all()
  assert not cfg_all
