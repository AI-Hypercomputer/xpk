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

import pytest
from .validation import validate_dependencies_list, SystemDependency


def test_validate_dependencies_list_returns_nothing_for_successful_validation(
    mocker,
):
  mocker.patch(
      'xpk.utils.validation.run_command_for_value', return_value=(0, '')
  )
  validate_dependencies_list([SystemDependency.DOCKER])


def test_validate_dependencies_list_exits_with_error_for_failed_validation(
    mocker,
):
  mocker.patch(
      'xpk.utils.validation.run_command_for_value', return_value=(1, '')
  )
  with pytest.raises(SystemExit):
    validate_dependencies_list([SystemDependency.DOCKER])
