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

import contextlib
import os
import tempfile
from typing import Iterator

from kubernetes.client.exceptions import ApiException
from kubernetes.dynamic import DynamicClient

from .console import xpk_print


def apply_kubectl_manifest(client, manifest) -> int:
  xpk_print('Applying manifest')
  dynamic_client = DynamicClient(client)

  status_code = 0
  for obj in manifest:
    api_version = obj['apiVersion']
    kind = obj['kind']
    namespace = obj.get('metadata', {}).get('namespace', 'default')

    api_resource = dynamic_client.resources.get(
        api_version=api_version, kind=kind
    )

    try:
      api_resource.get(name=obj['metadata']['name'], namespace=namespace)
      api_resource.patch(
          body=obj,
          namespace=namespace,
          name=obj['metadata']['name'],
          content_type='application/merge-patch+json',
      )
      xpk_print(
          f"Updated {kind} '{obj['metadata']['name']}' in namespace"
          f" '{namespace}'"
      )

    except ApiException as e:
      if e.status == 404:
        api_resource.create(body=obj, namespace=namespace)
        xpk_print(
            f"Applied {kind} '{obj['metadata']['name']}' in namespace"
            f" '{namespace}'"
        )
      else:
        xpk_print(f'Error applying {kind}: {e}')
        status_code = 1
  return status_code


@contextlib.contextmanager
def _set_env(key: str, value: str) -> Iterator[None]:
  environ = os.environ

  backup = environ.get(key)
  environ[key] = value
  try:
    yield
  finally:
    if backup is None:
      del environ[key]
    else:
      environ[key] = backup


@contextlib.contextmanager
def sandbox_kubeconfig() -> Iterator[None]:
  """Context manager to use a temporary k8s config file.

  This ensures that xpk operations do not interfere with the user's default
  k8s config file by limiting all operation into a temporary file for the
  duration of the context.

  We use KUBECONFIG environment so it's process wide and not thread safe.
  """

  with (
      tempfile.TemporaryDirectory(prefix='xpk-kube-') as dir_name,
      _set_env('KUBECONFIG', os.path.join(dir_name, 'config')),
  ):
    yield
