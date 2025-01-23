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
from ..utils.file import ensure_directory_exists
from ..utils.objects import hash_string
from shutil import copytree, copy
import requests
import os
import tempfile
import time


DockerRunCommandExitCode = 135
dockerBuildErrorCode = 134
ctk_dockerfile_path = "Dockerfile"
ctk_build_ref = "v1.45.1"
ctk_docker_image = "xpk-ctk"
ctk_container_name = "xpk-ctk-container"
gcloud_cfg_mount_path = "/root/.config/gcloud"
working_dir_mount_path = "/out"
dockerfile_gh_path = f"https://raw.githubusercontent.com/GoogleCloudPlatform/cluster-toolkit/refs/tags/{ctk_build_ref}/tools/cloud-build/images/cluster-toolkit-dockerfile/Dockerfile"
upload_dir_name = "uploads"


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
  def upload_file_to_working_dir(self, path: str, prefix: str = "") -> str:
    """Uploads single file to working directory.

    Args:
        path (str): path to file to upload

    Returns:
        str: path to a destination file
    """
    return ""

  @abstractmethod
  def upload_directory_to_working_dir(self, path: str, prefix: str = "") -> str:
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
      remove_container: bool = True,
  ) -> None:
    self.dockerfile_path = ""
    self.client = docker.from_env()
    self.gcloud_cfg_path = gcloud_cfg_path
    self.working_dir = working_dir
    self.nocache = nocache
    self.img_name = f"{img_name}:{ctk_build_ref}"
    self.container_name = container_name
    self.remove_container = remove_container

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
    xpk_print("Docker found!")

    if not self._docker_image_exists():
      xpk_print(f"Docker image {self.img_name} not found.")
      self._build_image()
    else:
      xpk_print(f"Docker image {self.img_name} found!")

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
    xpk_print(f"Running command: {cmd} ...")
    xpk_print(
        f"volumes: {self.gcloud_cfg_path}:{gcloud_cfg_mount_path},"
        f" {self.working_dir}:{working_dir_mount_path}"
    )
    try:
      container = self.client.containers.run(
          image=self.img_name,
          entrypoint=cmd,
          remove=self.remove_container,
          name=self._get_container_unique_name(
              cmd
          ),  # To allow multiple xpk commands run in one machine.
          detach=True,
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
      self._print_logs_from_container(container)
      result = container.wait()
      if result["StatusCode"] != 0:
        xpk_print(f"Running gcluster command: {cmd} failed.")
        xpk_exit(result["StatusCode"])
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

  def _print_logs_from_container(self, container):
    output = container.attach(stdout=True, stream=True, logs=True)
    for line in output:
      xpk_print(f"[gcluster] {line.decode('utf-8').strip()}")

  def upload_directory_to_working_dir(self, path: str, prefix: str = "") -> str:
    """Move file or directory from specified path to directory containing deployment files

    Args:
        path (str): path of directory/file that will be moved to deployment directory
    """
    name = path.split("/")[-1]
    target_path = os.path.join(self._get_upload_directory(prefix), name)
    uploaded_path = os.path.join(
        self._get_upload_directory_mounted(prefix), name
    )
    xpk_print(
        f"Copying directory from {path} to {target_path}. Path in docker:"
        f" {uploaded_path}"
    )
    copytree(path, target_path, dirs_exist_ok=True)
    return uploaded_path

  def upload_file_to_working_dir(self, path: str, prefix: str = "") -> str:
    """Move file or directory from specified path to directory containing deployment files

    Args:
        path (str): path of directory/file that will be moved to deployment directory
    """
    name = path.split("/")[-1]
    target_path = os.path.join(self._get_upload_directory(prefix), name)
    uploaded_path = os.path.join(
        self._get_upload_directory_mounted(prefix), name
    )
    xpk_print(
        f"Copying a file from {path} to {target_path}. Path in docker:"
        f" {uploaded_path}"
    )
    copy(path, target_path)
    return uploaded_path

  def _get_upload_directory(self, prefix: str = "") -> str:
    upload_dir = os.path.join(self.working_dir, upload_dir_name, prefix)
    ensure_directory_exists(upload_dir)
    return upload_dir

  def _get_upload_directory_mounted(self, prefix: str = "") -> str:
    return os.path.join(working_dir_mount_path, upload_dir_name, prefix)

  def _create_tmp_for_dockerfile(self) -> str:
    tmp_dir = os.path.join(tempfile.gettempdir(), "xpkutils")
    ensure_directory_exists(tmp_dir)
    tmp_path = os.path.join(tmp_dir, "Dockerfile")
    return tmp_path

  def _is_docker_installed(self) -> None:
    self.client.info()

  def _docker_image_exists(self) -> bool:
    try:
      self.client.images.get(f"{self.img_name}")
    except ImageNotFound as _:
      return False
    return True

  def _download_ctk_dockerfile(self) -> None:
    """Downloads cluster toolkit dockerfile to dockerfile_path

    Returns:
        None
    """
    xpk_print(f"Downloading Dockerfile from {dockerfile_gh_path} ...")
    self.dockerfile_path = self._create_tmp_for_dockerfile()
    r = requests.get(dockerfile_gh_path, timeout=100)
    with open(self.dockerfile_path, "w+", encoding="utf8") as dockerfile:
      dockerfile.write(r.text)
    xpk_print("Downloading Dockerfile completed!")

  def _build_image(self):
    try:
      self._download_ctk_dockerfile()
      dir_path = "/".join(self.dockerfile_path.split("/")[:-1])
      xpk_print(
          f"Building  {self.img_name} docker image from dockerfile:"
          f" {self.dockerfile_path}. It may take a while..."
      )
      self.client.images.build(
          nocache=self.nocache,
          path=dir_path,
          tag=f"{self.img_name}",
          rm=True,
          buildargs={"CLUSTER_TOOLKIT_REF": ctk_build_ref},
      )
    except BuildError as e:
      xpk_print(f"error while building image {self.img_name}: {e.msg}")
      xpk_exit(dockerBuildErrorCode)
    except APIError as e:
      xpk_print(f"erro while building image {self.img_name}: {e.explanation}")
      xpk_exit(dockerBuildErrorCode)
    except TypeError as e:
      xpk_print(f"TypeError while building image {self.img_name}: {e.args}")
      xpk_exit(dockerBuildErrorCode)
    xpk_print("Docker image build succesfully.")
    os.remove(self.dockerfile_path)
    tmp_dockerfile_dir = "/".join(self.dockerfile_path.split("/")[:-1])
    os.rmdir(tmp_dockerfile_dir)

  def _get_container_unique_name(self, cmd):
    return f"{self.container_name}_{hash_string(cmd + str(time.time_ns()))}"
