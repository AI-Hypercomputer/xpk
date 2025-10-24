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

import bisect
from abc import ABC, abstractmethod
from typing import List
from packaging.version import Version

from ..utils.console import xpk_print
from ..core.commands import (
    run_command_for_value,
    run_command_with_updates_retry,
)
from ..utils.file import make_tmp_file


class _Migration(ABC):

  @property
  @abstractmethod
  def version(self) -> Version:
    pass

  def run(self) -> int:
    code = self._pre_install()
    if code != 0:
      return code

    code = self.__install()
    if code != 0:
      return code

    return self._post_install()

  @abstractmethod
  def _pre_install(self) -> int:
    pass

  @abstractmethod
  def _post_install(self) -> int:
    pass

  def __install(self) -> int:
    return _install_kueue_manifest(self.version)


class _Migration_v0_13_0(_Migration):

  def __init__(self):
    self.cohorts_yaml_path = make_tmp_file("cohorts")

  @property
  def version(self) -> Version:
    return Version("v0.13.0")

  def _pre_install(self) -> int:
    code, _ = run_command_for_value(
        command=(
            "kubectl get cohorts.kueue.x-k8s.io -o yaml >"
            f" {self.cohorts_yaml_path}"
        ),
        task="Fetch existing Cohorts",
    )
    if code != 0:
      return code

    code, _ = run_command_for_value(
        command=(
            f"sed -i -e 's/v1alpha1/v1beta1/g' {self.cohorts_yaml_path} sed -i"
            " -e 's/^ parent: (\S*)$/ parentName: \1/'"
            f" {self.cohorts_yaml_path}"
        ),
        task="Replace v1alpha1 with v1beta1 in Cohorts",
    )
    if code != 0:
      return code

    code, _ = run_command_for_value(
        command="kubectl delete crd cohorts.kueue.x-k8s.io",
        task="Delete existing Cohorts CRD",
    )
    return code

  def _post_install(self) -> int:
    code, _ = run_command_for_value(
        command=f"kubectl apply -f {self.cohorts_yaml_path}",
        task="Apply updated Cohorts",
    )
    return code


class _Migration_v0_14_0(_Migration):

  def __init__(self):
    self.topologies_yaml_path = make_tmp_file("topologies")

  @property
  def version(self) -> Version:
    return Version("v0.14.0")

  def _pre_install(self) -> int:
    code, _ = run_command_for_value(
        command=(
            "kubectl get topologies.kueue.x-k8s.io -o yaml >"
            f" {self.topologies_yaml_path}"
        ),
        task="Fetch existing Topologies",
    )
    if code != 0:
      return code

    code, _ = run_command_for_value(
        command=f"sed -i -e 's/v1alpha1/v1beta1/g' {self.topologies_yaml_path}",
        task="Replace v1alpha1 with v1beta1 in Topologies",
    )
    if code != 0:
      return code

    code, _ = run_command_for_value(
        command="kubectl delete crd topologies.kueue.x-k8s.io",
        task="Delete existing Topologies CRD",
    )
    if code != 0:
      return code

    code, _ = run_command_for_value(
        command="""kubectl get topology.kueue.x-k8s.io -o jsonpath='{range .items[*]}{.metadata.name}{"\n"}{end}' | while read -r name; do kubectl patch topology.kueue.x-k8s.io "$name" -p '{"metadata":{"finalizers":[]}}' --type='merge' done""",
        task="Remove Finalizers from Topologies",
    )
    return code

  def _post_install(self) -> int:
    code, _ = run_command_for_value(
        command=f"kubectl apply -f {self.topologies_yaml_path}",
        task="Apply updated Cohorts",
    )
    return code


_MIGRATIONS: List[_Migration] = [_Migration_v0_13_0(), _Migration_v0_14_0()]


def _install_kueue_manifest(version: Version) -> int:
  manifest_url = f"https://github.com/kubernetes-sigs/kueue/releases/download/v{version}/manifests.yaml"
  install_command = (
      f"kubectl apply --server-side --force-conflicts -f {manifest_url}"
  )
  task = f"Installing Kueue v{version}"
  return_code = run_command_with_updates_retry(install_command, task)
  if return_code != 0:
    xpk_print(f"{task} returned ERROR {return_code}")
  return return_code


def install_kueue_manifest_upgrading(
    from_version: Version | None, to_version: Version
) -> int:
  """TODO"""
  if from_version is None:
    return _install_kueue_manifest(to_version)

  migration_i = bisect.bisect_right(
      _MIGRATIONS, from_version, key=lambda m: m.version
  )
  last_run_migration_version: Version | None = None

  while (
      migration_i < len(_MIGRATIONS)
      and _MIGRATIONS[migration_i].version <= to_version
  ):
    code = _MIGRATIONS[migration_i].run()
    last_run_migration_version = _MIGRATIONS[migration_i].version
    if code != 0:
      return code
    migration_i += 1

  if last_run_migration_version == to_version:
    return 0
  else:
    return _install_kueue_manifest(to_version)
