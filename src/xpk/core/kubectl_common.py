"""
Copyright 2026 Google LLC

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

from collections import defaultdict
from dataclasses import dataclass
import json
from typing import Any

from .commands import run_command_with_updates_retry


@dataclass(frozen=True)
class PatchResources:
  cpu_request: int | None = None
  cpu_limit: int | None = None
  memory_request: str | None = None
  memory_limit: str | None = None


_EMPTY_PATCH_RESOURCES = PatchResources()


def patch_controller_manager_resources(
    name: str,
    namespace: str,
    replicas: int | None = None,
    patch_resources: PatchResources | None = None,
) -> int:
  if replicas is None and patch_resources is None:
    return 0

  patch: dict[str, Any] = {"spec": {}}

  if replicas is not None:
    patch["spec"]["replicas"] = replicas

  if patch_resources and patch_resources != _EMPTY_PATCH_RESOURCES:
    resources: dict[str, dict[str, str]] = defaultdict(dict)
    if patch_resources.cpu_request is not None:
      resources["requests"]["cpu"] = str(patch_resources.cpu_request)
    if patch_resources.cpu_limit is not None:
      resources["limits"]["cpu"] = str(patch_resources.cpu_limit)
    if patch_resources.memory_request is not None:
      resources["requests"]["memory"] = patch_resources.memory_request
    if patch_resources.memory_limit is not None:
      resources["limits"]["memory"] = patch_resources.memory_limit
    patch["spec"]["template"] = {
        "spec": {
            "containers": [{
                "name": "manager",
                "resources": resources,
            }]
        }
    }

  patch_str = json.dumps(patch)
  patch_command = (
      f"kubectl patch deployment {name} -n {namespace}"
      f" --type='strategic' --patch='{patch_str}'"
  )
  return run_command_with_updates_retry(
      patch_command,
      "Updating Controller Manager resources",
  )
