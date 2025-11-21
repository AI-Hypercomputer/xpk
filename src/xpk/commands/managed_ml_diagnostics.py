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

from packaging.version import Version
from ..core.commands import run_command_for_value, run_command_with_updates
from ..utils.console import xpk_print
import os
import tempfile

_KUEUE_DEPLOYMENT_NAME = 'kueue-controller-manager'
_KUEUE_NAMESPACE_NAME = 'kueue-system'
_CERT_WEBHOOK_DEPLOYMENT_NAME = 'cert-manager-webhook'
_CERT_WEBHOOK_NAMESPACE_NAME = 'cert-manager'
_WEBHOOK_PACKAGE = 'mldiagnostics-injection-webhook'
_WEBHOOK_VERSION = Version('v0.5.0')
_WEBHOOK_FILENAME = f'{_WEBHOOK_PACKAGE}-v{_WEBHOOK_VERSION}.yaml'
_OPERATOR_PACKAGE = 'mldiagnostics-connection-operator'
_OPERATOR_VERSION = Version('v0.5.0')
_OPERATOR_FILENAME = f'{_OPERATOR_PACKAGE}-v{_OPERATOR_VERSION}.yaml'
_CERT_MANAGER_VERSION = Version('v1.13.0')


def _install_cert_manager(version: Version = _CERT_MANAGER_VERSION) -> int:
  """
  Apply the cert-manager manifest.

  Returns:
    0 if successful and 1 otherwise.
  """

  command = (
      'kubectl apply -f'
      ' https://github.com/cert-manager/cert-manager/releases/download/'
      f'v{version}/cert-manager.yaml'
  )

  return_code = run_command_with_updates(
      command, f'Applying cert-manager {version} manifest...'
  )

  return return_code


def _download_mldiagnostics_yaml(package_name: str, version: Version) -> int:
  """
  Downloads the mldiagnostics injection webhook YAML from Artifact Registry.

  Returns:
    0 if successful and 1 otherwise.
  """

  command = (
      'gcloud artifacts generic download'
      ' --repository=mldiagnostics-webhook-and-operator-yaml --location=us'
      f' --package={package_name} --version=v{version} --destination=/tmp/'
      ' --project=ai-on-gke'
  )

  return_code, return_output = run_command_for_value(
      command,
      f'Download {package_name} {version}...',
  )

  if return_code != 0:
    if 'already exists' in return_output:
      xpk_print(
          f'Artifact file for {package_name} {version} already exists locally.'
          ' Skipping download.'
      )
      return 0

  return return_code


def _create_mldiagnostics_namespace() -> int:
  """
  Creates the 'gke-mldiagnostics' namespace.

  Returns:
    0 if successful and 1 otherwise.
  """

  command = 'kubectl create namespace gke-mldiagnostics'

  return_code, return_output = run_command_for_value(
      command, 'Create gke-mldiagnostics namespace...'
  )

  if return_code != 0:
    if 'already exists' in return_output:
      xpk_print('Namespace already exists. Skipping creation.')
      return 0

  return return_code


def _install_mldiagnostics_yaml(artifact_filename: str) -> int:
  """
  Applies the mldiagnostics injection webhook YAML manifest.

  Returns:
    0 if successful and 1 otherwise.
  """
  full_artifact_path = os.path.join(tempfile.gettempdir(), artifact_filename)

  command = f'kubectl apply -f {full_artifact_path} -n gke-mldiagnostics'

  return run_command_with_updates(
      command,
      f'Install {full_artifact_path}...',
  )


def _label_default_namespace_mldiagnostics() -> int:
  """
  Labels the 'default' namespace with 'managed-mldiagnostics-gke=true'.

  Returns:
    0 if successful and 1 otherwise.
  """

  command = 'kubectl label namespace default managed-mldiagnostics-gke=true'

  return run_command_with_updates(
      command,
      'Label default namespace with managed-mldiagnostics-gke=true',
  )


def install_mldiagnostics_prerequisites() -> int:
  """
  Mldiagnostics installation requirements.

  Returns:
    0 if successful and 1 otherwise.
  """

  if not _wait_for_deployment_ready(
      deployment_name=_KUEUE_DEPLOYMENT_NAME, namespace=_KUEUE_NAMESPACE_NAME
  ):
    xpk_print(
        f'Application {_KUEUE_DEPLOYMENT_NAME} failed to become ready within'
        ' the timeout.'
    )
    return 1

  return_code = _install_cert_manager()
  if return_code != 0:
    return return_code

  cert_webhook_ready = _wait_for_deployment_ready(
      deployment_name=_CERT_WEBHOOK_DEPLOYMENT_NAME,
      namespace=_CERT_WEBHOOK_NAMESPACE_NAME,
  )
  if not cert_webhook_ready:
    xpk_print('The cert-manager-webhook installation failed.')
    return 1

  return_code = _download_mldiagnostics_yaml(
      package_name=_WEBHOOK_PACKAGE, version=_WEBHOOK_VERSION
  )
  if return_code != 0:
    return return_code

  return_code = _create_mldiagnostics_namespace()
  if return_code != 0:
    return return_code

  return_code = _install_mldiagnostics_yaml(artifact_filename=_WEBHOOK_FILENAME)
  if return_code != 0:
    return return_code

  return_code = _label_default_namespace_mldiagnostics()
  if return_code != 0:
    return return_code

  return_code = _download_mldiagnostics_yaml(
      package_name=_OPERATOR_PACKAGE, version=_OPERATOR_VERSION
  )
  if return_code != 0:
    return return_code

  return_code = _install_mldiagnostics_yaml(
      artifact_filename=_OPERATOR_FILENAME
  )
  if return_code != 0:
    return return_code

  xpk_print(
      'All mldiagnostics installation and setup steps have been'
      ' successfully completed!'
  )
  return 0


def _wait_for_deployment_ready(
    deployment_name: str, namespace: str, timeout_seconds: int = 300
) -> bool:
  """
  Polls the Kubernetes Deployment status using kubectl rollout status
  until it successfully rolls out (all replicas are ready) or times out.

  Args:
      deployment_name: The name of the Kubernetes Deployment (e.g., 'kueue-controller-manager').
      namespace: The namespace where the Deployment is located (e.g., 'kueue-system').
      timeout_seconds: Timeout duration in seconds (default is 300s / 5 minutes).

  Returns:
      bool: True if the Deployment successfully rolled out, False otherwise (timeout or error).
  """

  command = (
      f'kubectl rollout status deployment/{deployment_name} -n {namespace}'
      f' --timeout={timeout_seconds}s'
  )

  return_code = run_command_with_updates(
      command, f'Checking status of deployment {deployment_name}...'
  )

  if return_code != 0:
    return False

  # When the status changes to 'running,' it might need about 10 seconds to fully stabilize.
  stabilization_seconds = 30
  stabilization_command = f'sleep {stabilization_seconds}'
  stabilization_code = run_command_with_updates(
      stabilization_command,
      f'Deployment {deployment_name} is ready. Waiting {stabilization_seconds}'
      ' seconds for full stabilization',
      verbose=True,
  )
  if stabilization_code != 0:
    return False

  return True
