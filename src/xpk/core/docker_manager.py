"""
Copyright 2023 Google LLC

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

import docker
from ..utils.console import xpk_exit, xpk_print
from docker.errors import APIError, ImageNotFound

ctk_dockerfile_path = "Dockerfile"
ctk_docker_image = "xpk-ctk"
gcloud_cfg_mount_path = "/gcloud_cfg"
deployment_dir_mount_path = "/deployment"


class CtkDockerManager:
  """CtkDockerManager is a class for managing gcluster execution in docker container.
  Attributes:
    - dockerfile (str) : path to dockerfile defining gcluster execution image
    - gcloud_cfg_path (str) : path to directory containing gcloud configuration
    - deployment_dir (str) : path to directory in which gcluster deployment directory will be saved

  """

  def __init__(
      self, dockerfile_path: str, gcloud_cfg_path: str, deployment_dir: str
  ) -> None:
    self.dockerfile = dockerfile_path
    self.client = docker.from_env()
    self._img_name = ctk_dockerfile_path
    self._is_docker_installed()
    self.gcloud_cfg_path = gcloud_cfg_path
    self.deployment_dir = deployment_dir

  def _is_docker_installed(self) -> None:
    self.client.info()

  def _image_exists(self) -> bool:
    try:
      self.client.images.get(self._img_name)
    except ImageNotFound as _:
      xpk_print(f"Image {self._img_name} not found")
      return False
    return True

  def build_image(self):
    """Build image from dockerfile pointed by _img_name. This method
    uses python docker client to build cloud toolkit execution image.
    Arguments:
    Returns:
      - None
    Raises:
      - docker.errors.BuildError – If there is an error during the build.
      - docker.errors.APIError – If the server returns any other error.
      - TypeError - otherwise

    """
    if self._image_exists():
      return
    self.client.images.build(
        dockerfile=self.dockerfile, tag=f"{self._img_name}:latest"
    )

  def run_container(self):
    """Run container from _img_name and mount directories:
        - gcloud config
        - deployment directory
    Arguments:
    Returns:
      - None
    Raises:
      - docker.errors.ContainerError,
      - docker.errors.ImageNotFound,
      - docker.errors.APIError
    """
    self.client.containers.run(
        self._img_name,
        volumes={
            gcloud_cfg_mount_path: {"bind": self.gcloud_cfg_path},
            deployment_dir_mount_path: {"bind": self.deployment_dir},
        },
    )

  def upload_file(self, file: str):
    pass

  def upload_dir(self, dir_path: str):
    pass
