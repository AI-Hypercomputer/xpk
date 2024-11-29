"""
Copyright 2024 Google LLC

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

from abc import ABC, abstractmethod
import docker
from docker.errors import ContainerError, APIError, ImageNotFound, BuildError
from ..utils.console import xpk_print, xpk_exit
from shutil import move
import requests
import os
import tempfile


DockerRunCommandExitCode = 135
dockerBuildErrorCode = 134
ctk_dockerfile_path = "Dockerfile"
ctk_docker_image = "xpk-ctk"
ctk_container_name = "xpk-ctk-container"
gcloud_cfg_mount_path = "/root/.config/gcloud"
deployment_dir_mount_path = "/out"


class CtkCommandRunner(ABC):
  """This is a base class that defines methods a class for running cluster toolkit command should implement."""

  @abstractmethod
  def build(self) -> None:
    return None

  @abstractmethod
  def run_command(self, cmd: str) -> None:
    return None

  @abstractmethod
  def upload_to_deployment_dir(self, path: str) -> None:
    return None


class CtkDockerManager(CtkCommandRunner):
  """CtkDockerManager is a class for managing gcluster execution in docker container.
  Attributes:
    - dockerfile_path (str) : path to dockerfile defining gcluster execution image
    - gcloud_cfg_path (str) : path to directory containing gcloud configuration
    - deployment_dir (str) : path to directory in which gcluster deployment directory will be saved

  """

  def __init__(
      self,
      gcloud_cfg_path: str,
      deployment_dir: str,
      nocache: bool = False,
      img_name: str = ctk_docker_image,
      container_name: str = ctk_container_name,
      rm_container_after: bool = True,
  ) -> None:

    self.client = docker.from_env()
    self._is_docker_installed()
    self.gcloud_cfg_path = gcloud_cfg_path
    self.deployment_dir = deployment_dir
    self.nocache = nocache
    self.img_name = img_name
    self.container_name = container_name
    self.rm_container_after = rm_container_after
    self.dockerfile_path = self._create_tmp_for_dockerfile()
    self._download_ctk_dockerfile()

  def _create_tmp_for_dockerfile(self) -> str:
    os.mkdir(os.path.join(tempfile.gettempdir(), "xpkutils"))
    tmp_path = os.path.join(tempfile.gettempdir(), "xpkutils", "Dockerfile")
    return tmp_path

  def _is_docker_installed(self) -> None:
    self.client.info()

  def _download_ctk_dockerfile(self):
    """Downloads cluster toolkit dockerfile and returns tmp path on which it is saved

    Returns:
        str: path do dockerfile
    """
    r = requests.get(
        "https://raw.githubusercontent.com/GoogleCloudPlatform/cluster-toolkit/9e9a03f6e3e1cdb82449a8e512e4dfc98c123b12/tools/cloud-build/images/cluster-toolkit-dockerfile/Dockerfile",
        timeout=100,
    )

    with open(self.dockerfile_path, "w+", encoding="utf8") as dockerfile:
      dockerfile.write(r.text)

  def _image_exists(self, img_name: str) -> bool:
    try:
      self.client.images.get(img_name)
    except ImageNotFound as _:
      xpk_print(f"Image {img_name} not found")
      return False
    return True

  def build(self):
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
    dir_path = "/".join(self.dockerfile_path.split("/")[:-1])
    xpk_print(f"Building docker image from dockerfile: {self.dockerfile_path}. It may take a while...")
    if self.nocache is False and self._image_exists(self.img_name):
      return
    try:
      self.client.images.build(
          nocache=self.nocache,
          path=dir_path,
          tag=f"{self.img_name}:latest",
          rm=True,
      )
    except BuildError as e:
      xpk_print(f"error while building image {self.img_name}: {e.msg}")
      xpk_exit(dockerBuildErrorCode)
    except APIError as e:
      xpk_print(f"erro while building image {self.img_name}: {e.explanation}")
      xpk_exit(dockerBuildErrorCode)
    except TypeError as e:
      xpk_print(f"TypeError while building image {self.img_name}")
      xpk_exit(dockerBuildErrorCode)
    xpk_print("Docker image build succesfully.")
    os.remove(self.dockerfile_path)
    tmp_dockerfile_dir = "/".join(self.dockerfile_path.split("/")[:-1])
    os.rmdir(tmp_dockerfile_dir)

  def run_command(
      self,
      cmd: str,
  ) -> None:
    """Run container from _img_name and mount directories:
        - gcloud config
        - deployment directory
    Arguments:
    Returns:
      - bytes
    Raises:
      - docker.errors.ContainerError,
      - docker.errors.ImageNotFound,
      - docker.errors.APIError
    """
    xpk_print(f"Running command: {cmd} inside container: {self.container_name}")
    try:
      self.client.containers.run(
          image=self.img_name,
          entrypoint=cmd,
          remove=self.rm_container_after,
          name=self.container_name,
          stdout=True,
          stderr=True,
          volumes=[
              f"{self.gcloud_cfg_path}:{gcloud_cfg_mount_path}",
              f"{self.deployment_dir}:{deployment_dir_mount_path}",
          ],
      )
    except ContainerError as e:
      xpk_print(
          "Deploying cluster failed due to ContainerError with exit status:"
          f" {e.exit_status} and stderr: {e.stderr}"
      )
      xpk_exit(DockerRunCommandExitCode)
    except ImageNotFound as _:
      xpk_print(f"Image {ctk_docker_image} not found. Deploying cluster failed")
      xpk_exit(DockerRunCommandExitCode)
    except APIError as e:
      xpk_print(f"Deploying cluster toolkit failed due to {e.explanation}")
      xpk_exit(DockerRunCommandExitCode)

  def upload_to_deployment_dir(self, path: str):
    """Move file or directory from specified path to directory containing deployment files

    Args:
        path (str): path of directory/file that will be moved to deployment directory
    """
    move(path, self.deployment_dir)
