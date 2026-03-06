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
from .validation import (
    validate_dependencies_list,
    SystemDependency,
    should_validate_dependencies,
)
from xpk.utils.validation import FeatureFlags


class Args:
  pass


def test_should_validate_dependencies_returns_true_by_default():
  assert should_validate_dependencies(Args())


def test_should_validate_dependencies_returns_false_if_skip_validation():
  args = Args()
  args.skip_validation = True
  assert not should_validate_dependencies(args)


def test_should_validate_dependencies_returns_false_if_dry_run():
  args = Args()
  args.dry_run = True
  assert not should_validate_dependencies(args)


def test_should_validate_dependencies_returns_true_if_both_are_false():
  args = Args()
  args.skip_validation = False
  args.dry_run = False
  assert should_validate_dependencies(args)


def test_validate_dependencies_list_returns_nothing_for_successful_validation(
    mocker,
):
  mocker.patch(
      'xpk.utils.validation.run_command_for_value', return_value=(0, '')
  )
  validate_dependencies_list(Args(), [SystemDependency.DOCKER])


def test_validate_dependencies_list_exits_with_error_for_failed_validation(
    mocker,
):
  mocker.patch(
      'xpk.utils.validation.run_command_for_value', return_value=(1, '')
  )
  with pytest.raises(SystemExit):
    validate_dependencies_list(Args(), [SystemDependency.DOCKER])


def test_validate_dependencies_list_downloads_dependency_if_feature_flag_enabled(
    mocker,
):
  mocker.patch(
      'xpk.utils.validation.run_command_for_value', return_value=(0, '')
  )
  mock_ensure = mocker.patch('xpk.utils.validation.ensure_dependency')
  FeatureFlags.DEPENDENCY_AUTO_DOWNLOAD = True

  validate_dependencies_list(Args(), [SystemDependency.KUBECTL])

  mock_ensure.assert_called_once_with(
      SystemDependency.KUBECTL.value.binary_dependency.value
  )


def test_validate_dependencies_list_skips_download_if_feature_flag_disabled(
    mocker,
):
  mocker.patch(
      'xpk.utils.validation.run_command_for_value', return_value=(0, '')
  )
  mock_ensure = mocker.patch('xpk.utils.validation.ensure_dependency')
  FeatureFlags.DEPENDENCY_AUTO_DOWNLOAD = False

  validate_dependencies_list(Args(), [SystemDependency.KUBECTL])

  mock_ensure.assert_not_called()


def test_validate_dependencies_list_skips_download_if_no_binary_dependency(
    mocker,
):
  mocker.patch(
      'xpk.utils.validation.run_command_for_value', return_value=(0, '')
  )
  mock_ensure = mocker.patch('xpk.utils.validation.ensure_dependency')
  FeatureFlags.DEPENDENCY_AUTO_DOWNLOAD = True

  validate_dependencies_list(Args(), [SystemDependency.DOCKER])

  mock_ensure.assert_not_called()


def test_validate_dependencies_list_skips_download_if_args_flag_disabled(
    mocker,
):
  mocker.patch(
      'xpk.utils.validation.run_command_for_value', return_value=(0, '')
  )
  mock_ensure = mocker.patch('xpk.utils.validation.ensure_dependency')
  FeatureFlags.DEPENDENCY_AUTO_DOWNLOAD = True
  args = Args()
  args.dependency_auto_download = False

  validate_dependencies_list(args, [SystemDependency.KUBECTL])

  mock_ensure.assert_not_called()


def test_validate_dependencies_list_downloads_dependency_if_args_flag_enabled(
    mocker,
):
  mocker.patch(
      'xpk.utils.validation.run_command_for_value', return_value=(0, '')
  )
  mock_ensure = mocker.patch('xpk.utils.validation.ensure_dependency')
  FeatureFlags.DEPENDENCY_AUTO_DOWNLOAD = True
  args = Args()
  args.dependency_auto_download = True

  validate_dependencies_list(args, [SystemDependency.KUBECTL])

  mock_ensure.assert_called_once_with(
      SystemDependency.KUBECTL.value.binary_dependency.value
  )
