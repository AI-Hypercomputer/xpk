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

import datetime
import os
import random
import string

from ..utils.console import xpk_exit, xpk_print
from ..utils.file import write_tmp_file
from .commands import run_command_with_updates

DEFAULT_DOCKER_IMAGE = 'python:3.10'
DEFAULT_SCRIPT_DIR = os.getcwd()
PLATFORM = 'linux/amd64'


class DockerImageManager:
  """Manages Docker images by validating, building, tagging, and uploading them."""

  def __init__(self, args):
    self.args = args

  def validate_docker_image(self) -> int:
    """Validates that the user provided docker image exists in your project.

    Returns:
      0 if successful and 1 otherwise.
    """
    if not self.args.docker_image or not any(
        repo in self.args.docker_image for repo in ['gcr.io', 'docker.pkg.dev']
    ):
      return 0

    command = (
        f'gcloud container images describe {self.args.docker_image} --project'
        f' {self.args.project}'
    )
    return_code = run_command_with_updates(
        command, 'Validate Docker Image', self.args, verbose=False
    )
    if return_code != 0:
      xpk_print(
          'Failed to validate your docker image, check that the docker image'
          f' exists. You may be able to find the {self.args.docker_image} in'
          f' {self.args.project}. If the docker image exists, the service'
          ' account of this project maybe be missing the permissions to access'
          ' the docker image.'
      )

    return return_code

  def build_docker_image_from_base_image(self, verbose=True) -> tuple[int, str]:
    """Adds script dir to the base docker image and uploads the image.

    Returns:
      Tuple of:
        0 if successful and 1 otherwise.
        Name of the Docker image created.
    """
    # Pick a name for the docker image.
    docker_image_prefix = os.getenv('USER', 'unknown')
    docker_name = f'{docker_image_prefix}-runner'

    script_dir_dockerfile = """FROM {base_docker_image}

  # Set the working directory in the container
  WORKDIR /app

  # Copy all files from local workspace into docker container
  COPY . .

  WORKDIR /app
  """

    docker_file = script_dir_dockerfile.format(
        base_docker_image=self.args.base_docker_image,
    )
    tmp = write_tmp_file(docker_file)
    docker_build_command = (
        f'docker buildx build --platform={PLATFORM} -f {str(tmp.file.name)} -t'
        f' {docker_name} {self.args.script_dir}'
    )

    xpk_print(f'Building {self.args.script_dir} into docker image.')
    return_code = run_command_with_updates(
        docker_build_command,
        'Building script_dir into docker image',
        self.args,
        verbose=verbose,
    )
    if return_code != 0:
      xpk_print(
          'Failed to add script_dir to docker image, check the base docker'
          ' image. You should be able to navigate to the URL'
          f' {self.args.base_docker_image} in {self.args.project}.'
      )
      xpk_exit(1)

    tag = self.generate_docker_tag(docker_name)
    xpk_print(f'Adding Docker Image: {tag} to {self.args.project}')

    return_code = self.tag_and_upload_image(docker_name, tag)
    return return_code, tag

  def setup_docker_image(self) -> tuple[int, str]:
    """Does steps to verify docker args, check image, and build image (if asked).

    Returns:
      tuple:
        0 if successful and 1 otherwise.
        Name of the docker image to use.
    """
    if self.use_base_docker_image_or_docker_image():
      if self.validate_docker_image() != 0:
        xpk_exit(1)
      return self.build_docker_image_from_base_image()

    if self.validate_docker_image() != 0:
      xpk_exit(1)

    return 0, self.args.docker_image

  def use_base_docker_image_or_docker_image(self) -> bool:
    """Checks for correct docker image arguments.

    Returns:
      True if intended to use base docker image, False to use docker image.
    """
    # Check if (base_docker_image and script_dir) or (docker_image) is set.
    if self.args.docker_image:
      if self.args.script_dir != DEFAULT_SCRIPT_DIR:
        xpk_print(
            '`--script-dir` and --docker-image can not be used together. Please'
            ' see `--help` command for more details.'
        )
        xpk_exit(1)
      if self.args.base_docker_image != DEFAULT_DOCKER_IMAGE:
        xpk_print(
            '`--base-docker-image` and --docker-image can not be used together.'
            ' Please see `--help` command for more details.'
        )
        xpk_exit(1)
      return False

    return True

  def generate_docker_tag(self, docker_name: str) -> str:
    """Generates a unique tag for the Docker image."""

    tag_random_prefix = ''.join(random.choices(string.ascii_lowercase, k=4))
    tag_datetime = datetime.datetime.now().strftime('%Y-%m-%d-%H-%M-%S')
    return f'gcr.io/{self.args.project}/{docker_name}:{tag_random_prefix}-{tag_datetime}'

  def tag_and_upload_image(
      self, docker_name: str, cloud_docker_image: str
  ) -> int:
    """Tags and uploads the Docker image."""

    xpk_print(f'Tagging Docker image {docker_name} as {cloud_docker_image}.')
    return_code = run_command_with_updates(
        f'docker tag {docker_name} {cloud_docker_image}',
        'Tag Docker Image',
        self.args,
        verbose=True,
    )
    if return_code != 0:
      xpk_print(
          'Failed to tag Docker image.'
          f' You should be able to navigate to the URL {cloud_docker_image} in'
          f' {self.args.project}.'
      )
      xpk_exit(1)

    xpk_print(f'Uploading Docker image {cloud_docker_image}.')
    return_code = run_command_with_updates(
        f'docker push {cloud_docker_image}',
        'Upload Docker Image',
        self.args,
        verbose=True,
    )
    if return_code != 0:
      xpk_print(
          'Failed to upload docker image.'
          f' You should be able to navigate to the URL {cloud_docker_image} in'
          f' {self.args.project}.'
      )
      xpk_exit(1)

    return return_code
