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
from shutil import copytree, copy
import requests
import os
import tempfile


DockerRunCommandExitCode = 135
dockerBuildErrorCode = 134
ctk_dockerfile_path = "Dockerfile"
ctk_docker_image = "xpk-ctk"
ctk_container_name = "xpk-ctk-container"
gcloud_cfg_mount_path = "/root/.config/gcloud"
working_dir_mount_path = "/out"
dockerfile_gh_path = "https://raw.githubusercontent.com/GoogleCloudPlatform/cluster-toolkit/refs/heads/develop/tools/cloud-build/images/cluster-toolkit-dockerfile/Dockerfile"
upload_dir = "uploads"


class CommandRunner(ABC):
  """This is a base class that defines methods a class for running cluster toolkit command should implement."""

  @abstractmethod
  def initialize(self) -> None:
    """initialize is a method that should implement all steps neccessary to run command.

    Returns:
        None
    """
    return None

  @abstractmethod
  def run_command(self, cmd: str) -> None:
    """run_command implements executing command. If command execution fails, exception should be raised.

    Args:
        cmd (str): command to run

    Returns:
        None:
    """
    return None

  @abstractmethod
  def upload_file_to_working_dir(self, path: str) -> str:
    """Uploads single file to working directory.

    Args:
        path (str): path to file to upload

    Returns:
        str: path to a destination file
    """
    return ""

  @abstractmethod
  def upload_directory_to_working_dir(self, path: str) -> str:
    """upload directory and its content to working directory.

    Args:
        path (str): path pointing to directory that will be uploaded.

    Returns:
        str: path to a target directory.
    """
    return ""


class DockerManager(CommandRunner):
  """DockerManager is a class for managing gcluster execution in docker container.
  Attributes:
    - dockerfile_path (str) : path to dockerfile defining gcluster execution image
    - gcloud_cfg_path (str) : path to directory containing gcloud configuration
    - working_dir (str) : path to directory in which gcluster deployment directory will be saved
    - client (DockerClient) : docker client
    - nocache (bool) : wheter to use docker cache when building image
    - img_name (str) : name of docker image to create
    - container_name (str) : name of the container that will be created from img_name
    - rm_container_after (bool) : if set to True, docker container in which command is executed will be removed after each execution.
  """

  def __init__(
      self,
      gcloud_cfg_path: str,
      working_dir: str,
      nocache: bool = False,
      img_name: str = ctk_docker_image,
      container_name: str = ctk_container_name,
      rm_container_after: bool = True,
  ) -> None:
    self.dockerfile_path = ""
    self.client = docker.from_env()
    self.gcloud_cfg_path = gcloud_cfg_path
    self.working_dir = working_dir
    self.nocache = nocache
    self.img_name = img_name
    self.container_name = container_name
    self.rm_container_after = rm_container_after

  def _create_tmp_for_dockerfile(self) -> str:
    tmp_dir = os.path.join(tempfile.gettempdir(), "xpkutils")
    if not os.path.exists(tmp_dir):
      os.mkdir(tmp_dir)
    tmp_path = os.path.join(tmp_dir, "Dockerfile")
    return tmp_path

  def _is_docker_installed(self) -> None:
    self.client.info()

  def _download_ctk_dockerfile(self) -> None:
    """Downloads cluster toolkit dockerfile to dockerfile_path

    Returns:
        None
    """
    r = requests.get(dockerfile_gh_path, timeout=100)

    with open(self.dockerfile_path, "w+", encoding="utf8") as dockerfile:
      dockerfile.write(r.text)

  def _image_exists(self, img_name: str) -> bool:
    try:
      self.client.images.get(img_name)
    except ImageNotFound as _:
      xpk_print(f"Image {img_name} not found")
      return False
    return True

  def initialize(self):
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
    self._is_docker_installed()
    self.dockerfile_path = self._create_tmp_for_dockerfile()
    dir_path = "/".join(self.dockerfile_path.split("/")[:-1])
    xpk_print(
        f"Building docker image from dockerfile: {self.dockerfile_path}. It may"
        " take a while..."
    )
    if self.nocache is False and self._image_exists(self.img_name):
      return
    try:
      self._download_ctk_dockerfile()
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
    xpk_print(
        f"volumes: {self.gcloud_cfg_path}:{gcloud_cfg_mount_path},"
        f" {self.working_dir}:{working_dir_mount_path}"
    )
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
              f"{self.working_dir}:{working_dir_mount_path}",
          ],
          environment={
              "GOOGLE_APPLICATION_CREDENTIALS": (
                  "/root/.config/gcloud/application_default_credentials.json"
              )
          },
      )
    except ContainerError as e:
      xpk_print(
          "Running command failed due to ContainerError with exit status:"
          f" {e.exit_status} and stderr: {e.stderr}"
      )
      xpk_exit(DockerRunCommandExitCode)
    except ImageNotFound as _:
      xpk_print(f"Image {ctk_docker_image} not found. Deploying cluster failed")
      xpk_exit(DockerRunCommandExitCode)
    except APIError as e:
      xpk_print(f"Deploying cluster toolkit failed due to {e.explanation}")
      xpk_exit(DockerRunCommandExitCode)

  def upload_directory_to_working_dir(self, path: str) -> str:
    """Move file or directory from specified path to directory containing deployment files

    Args:
        path (str): path of directory/file that will be moved to deployment directory
    """
    name = path.split("/")[-1]
    target_path = os.path.join(self.working_dir, upload_dir, name)
    if not os.path.exists(os.path.join(self.working_dir, upload_dir)):
      os.mkdir(os.path.join(self.working_dir, upload_dir))
    xpk_print(f"copying folder from {path} to {target_path}")
    copytree(path, target_path)
    return target_path

  def upload_file_to_working_dir(self, path: str) -> str:
    """Move file or directory from specified path to directory containing deployment files

    Args:
        path (str): path of directory/file that will be moved to deployment directory
    """
    name = path.split("/")[-1]
    target_path = os.path.join(self.working_dir, upload_dir, name)
    if not os.path.exists(os.path.join(self.working_dir, upload_dir)):
      os.mkdir(os.path.join(self.working_dir, upload_dir))
    xpk_print(f"copying file from {path} to {target_path}")
    copy(path, target_path)
    return target_path
