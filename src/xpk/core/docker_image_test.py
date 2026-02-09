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
from pytest_mock import MockerFixture
from .docker_image import build_docker_image_from_base_image
from .testing.commands_tester import CommandsTester
from .system_characteristics import DockerPlatform
from ..utils.feature_flags import FeatureFlags
from ..utils.execution_context import is_dry_run


@pytest.fixture(autouse=True)
def setup_mocks(mocker: MockerFixture):
  mocker.patch("xpk.core.docker_image.is_dry_run", return_value=True)


@pytest.fixture(autouse=True)
def commands_tester(mocker: MockerFixture) -> CommandsTester:
  return CommandsTester(mocker)


@pytest.fixture(autouse=True)
def command_args(mocker: MockerFixture):
  return mocker.Mock(
      cluster="cluster",
      project="project",
      zone="zone",
      script_dir="script_dir",
      base_docker_image="base_docker_image",
  )


def test_build_docker_image_from_base_image_uses_docker_if_feature_flag_disabled(
    commands_tester: CommandsTester, command_args
):
  FeatureFlags.CRANE_WORKLOADS_ENABLED = False

  return_code, image = build_docker_image_from_base_image(
      command_args, DockerPlatform.ARM
  )

  assert return_code == 0
  assert image == "gcr.io/project/dry-run-runner:prefix-current"
  commands_tester.assert_command_run(
      "docker buildx build --platform=linux/arm64",
      "-t dry-run-runner",
      "script_dir",
  )
  commands_tester.assert_command_run(
      "docker tag dry-run-runner gcr.io/project/dry-run-runner:prefix-current"
  )
  commands_tester.assert_command_run(
      "docker push gcr.io/project/dry-run-runner:prefix-current"
  )


def test_build_docker_image_from_base_image_uses_crane_if_feature_flag_enabled(
    commands_tester: CommandsTester, command_args
):
  FeatureFlags.CRANE_WORKLOADS_ENABLED = True

  return_code, image = build_docker_image_from_base_image(
      command_args, DockerPlatform.ARM
  )

  assert return_code == 0
  assert image == "gcr.io/project/dry-run-runner:prefix-current"
  commands_tester.assert_command_run(
      "crane mutate base_docker_image",
      "--append",
      "--platform linux/arm64",
      "--tag gcr.io/project/dry-run-runner:prefix-current",
      "--workdir /app",
  )
