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

from .config import xpk_config, CLIENT_ID_KEY
from .telemetry import generate_client_id


def test_generates_client_id_when_its_not_present():
  xpk_config.set(CLIENT_ID_KEY, None)
  generate_client_id()
  assert xpk_config.get(CLIENT_ID_KEY) is not None


def test_does_not_generate_client_id_when_its_present():
  client_id = '1337'
  xpk_config.set(CLIENT_ID_KEY, client_id)
  generate_client_id()
  assert xpk_config.get(CLIENT_ID_KEY) == client_id
