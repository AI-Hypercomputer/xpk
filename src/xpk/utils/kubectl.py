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

from kubernetes.client.exceptions import ApiException
from kubernetes.dynamic import DynamicClient

from .console import xpk_print


def apply_kubectl_manifest(client, manifest):
  xpk_print('Applying manifest')
  dynamic_client = DynamicClient(client)

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
