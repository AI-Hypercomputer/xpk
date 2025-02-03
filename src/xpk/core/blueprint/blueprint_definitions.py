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

from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class DeploymentModule:
  """DeploymentModule represents cluster toolkit deployment module

  Attributes:
    id (str): module name
    source (str): cluster toolkit source
    settings (dict[str, Any]): module settings
    use (list[str]): modules on which module depends
    outputs (list[str]): module outputs in cluster toolkit
  """

  id: str
  source: str
  outputs: Optional[list[str]] = None
  settings: Optional[dict[str, Any]] = None
  use: Optional[list[str]] = None


@dataclass
class DeploymentGroup:
  """DeploymentGroup represents cluster toolkit deployment group

  Attributes:
    group (str): deployment group name
    modules (list[DeploymentModule]): deployments modules
  """

  modules: list[DeploymentModule]
  group: Optional[str]


@dataclass
class Blueprint:
  """A class to represent Cluster Toolkit blueprint"""

  deployment_groups: list[DeploymentGroup]
  terraform_backend_defaults: Optional[dict]
  blueprint_name: Optional[str]
  toolkit_modules_url: str
  toolkit_modules_version: str
  vars: dict[str, str | list[str]] | None
