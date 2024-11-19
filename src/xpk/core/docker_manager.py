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
from ..utils.console import xpk_print
from docker.errors import ImageNotFound
from shutil import move

ctk_dockerfile_path = "Dockerfile"
ctk_docker_image = "xpk-ctk"
gcloud_cfg_mount_path = "/gcloud_cfg"
deployment_dir_mount_path = "/deployment"
xpk_ctk_img_name = "gcluster-xpk"


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
    self._is_docker_installed()
    self.gcloud_cfg_path = gcloud_cfg_path
    self.deployment_dir = deployment_dir

  def _is_docker_installed(self) -> None:
    self.client.info()

  def _image_exists(self, img_name: str) -> bool:
    try:
      self.client.images.get(img_name)
    except ImageNotFound as _:
      xpk_print(f"Image {img_name} not found")
      return False
    return True

  def build_image(
      self, img_name: str = xpk_ctk_img_name, nocache: bool = False
  ):
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
    dir_path = "/".join(self.dockerfile.split("/")[:-1])

    if nocache is False and self._image_exists(img_name):
      return
    self.client.images.build(
        nocache=nocache, path=dir_path, tag=f"{img_name}:latest", rm=True
    )

  def run_command(
      self,
      img_name: str,
      cmd: str,
      rm_container_after: bool = True,
      container_name: str = "xpk-gcluster",
  ) -> bytes:
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
    output = self.client.containers.run(
        image=img_name,
        command=cmd,
        remove=rm_container_after,
        name=container_name,
        stdout=True,
        stderr=True,
        volumes=[
            f"{self.gcloud_cfg_path}:{gcloud_cfg_mount_path}",
            f"{self.deployment_dir}:{deployment_dir_mount_path}",
        ],
    )
    return output

  def upload_to_deployment_dir(self, path: str):
    """Move file or directory from specified path to directory containing deployment files

    Args:
        file (str): path of directory/file that will be moved to deployment directory
    """
    move(path, self.deployment_dir)
