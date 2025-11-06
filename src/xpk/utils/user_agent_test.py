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

from .user_agent import get_user_agent


def test_get_user_agent_returns_correct_value_for_windows(mocker):
  mocker.patch('xpk.utils.user_agent.xpk_version', 'v1.0.0')
  mocker.patch('platform.system', return_value='Windows')
  mocker.patch('platform.version', return_value='10.0')
  assert get_user_agent() == 'XPK/v1.0.0 (Windows NT 10.0)'


def test_get_user_agent_returns_correct_value_for_linux(mocker):
  mocker.patch('xpk.utils.user_agent.xpk_version', 'v1.0.0')
  mocker.patch('platform.system', return_value='Linux')
  mocker.patch('platform.machine', return_value='x86_64')
  assert get_user_agent() == 'XPK/v1.0.0 (Linux; x86_64)'


def test_get_user_agent_returns_correct_value_for_darwin(mocker):
  mocker.patch('xpk.utils.user_agent.xpk_version', 'v1.0.0')
  mocker.patch('platform.system', return_value='Darwin')
  mocker.patch('platform.mac_ver', return_value=('10.15', '', 'x86_64'))
  assert get_user_agent() == 'XPK/v1.0.0 (Macintosh; x86_64 Mac OS X 10.15)'


def test_get_user_agent_returns_correct_value_for_unknown(mocker):
  mocker.patch('xpk.utils.user_agent.xpk_version', 'v1.0.0')
  mocker.patch('platform.system', return_value='Unknown')
  assert get_user_agent() == 'XPK/v1.0.0 ()'
