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

import docker
from docker.errors import APIError
from xpk.core.docker_manager import DockerManager, ctk_build_ref
import pytest
import os
import time

test_cfg_path = '/tmp/xpk_gcloud_cfg'
test_deployment_dir = '/tmp/xpk_deployment'
test_gcluster_cmd = 'gcluster --version'
test_ctk_xpk_img = 'gcluster-xpk'
test_ctk_xpk_container = 'xpk-test-container'


def remove_img():
  dc = docker.from_env()
  try:
    dc.images.remove(test_ctk_xpk_img, force=True)
  except APIError as _:
    pass


def remove_container():
  dc = docker.from_env()
  try:
    container = dc.containers.get(test_ctk_xpk_container)
    container.remove(force=True)
  except APIError as _:
    pass


def create_tmp_dirs():
  os.mkdir(test_cfg_path)
  os.mkdir(test_deployment_dir)


def remove_tmp_dirs():
  os.removedirs(test_cfg_path)
  os.removedirs(test_deployment_dir)


@pytest.fixture(name='setup_img_name')
def remove_test_ctk_img():
  create_tmp_dirs()
  remove_container()
  remove_img()
  yield test_ctk_xpk_img
  remove_container()
  remove_img()
  remove_tmp_dirs()


def test_docker_build_image(setup_img_name):
  dm = DockerManager(
      gcloud_cfg_path=test_cfg_path,
      working_dir=test_deployment_dir,
      img_name=setup_img_name,
  )
  dm.initialize()

  dc = docker.from_env()
  containers_before = dc.containers.list(all=True)
  dc.images.get(f'{setup_img_name}:{ctk_build_ref}')
  containers_after = dc.containers.list(all=True)
  assert len(containers_before) == len(containers_after)


def test_run_command(setup_img_name):

  dm = DockerManager(
      gcloud_cfg_path=test_cfg_path,
      working_dir=test_deployment_dir,
      img_name=setup_img_name,
      remove_container=True,
  )
  dc = docker.from_env()

  containers_before = dc.containers.list(all=True)
  dm.initialize()
  dm.run_command(test_gcluster_cmd)

  time.sleep(2)

  containers_after = dc.containers.list(all=True)

  assert len(containers_after) - len(containers_before) == 0
