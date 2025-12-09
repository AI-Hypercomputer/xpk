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

import yaml
from google.api_core.exceptions import PermissionDenied
from google.cloud import resourcemanager_v3
from kubernetes import client as k8s_client
from kubernetes import config
from kubernetes.client.exceptions import ApiException

from ..utils.console import xpk_exit, xpk_print
from .capacity import H200_DEVICE_TYPE
from .commands import (
    run_command_for_value,
    run_command_with_updates,
    run_command_with_updates_retry,
)
from .gcloud_context import (
    add_zone_and_project,
    get_cluster_location,
    zone_to_region,
)
from .resources import get_cluster_system_characteristics
from .system_characteristics import INSTALLER_NCCL_TCPXO, SystemCharacteristics

JOBSET_VERSION = 'v0.8.0'
PATHWAYS_JOB_VERSION = 'v0.1.4'
NRI_DEVICE_INJECTOR = 'https://raw.githubusercontent.com/GoogleCloudPlatform/container-engine-accelerators/master/nri_device_injector/nri-device-injector.yaml'

DEFAULT_NAMESPACE = 'default'
XPK_SA = 'xpk-sa'


# TODO(vbarr): Remove this function when jobsets gets enabled by default on
# GKE clusters.
def set_jobset_on_cluster(args) -> int:
  """Add jobset command on server side and ask user to verify it is created.

  Args:
    args: user provided arguments for running the command.

  Returns:
    0 if successful and 1 otherwise.
  """
  command = (
      'kubectl apply --server-side --force-conflicts'
      f' -f https://github.com/kubernetes-sigs/jobset/releases/download/{JOBSET_VERSION}/manifests.yaml'
  )
  task = f'Install Jobset on {args.cluster}'
  return_code = run_command_with_updates_retry(command, task)

  if return_code != 0:
    xpk_print(f'{task} returned with ERROR {return_code}.\n')
    xpk_print(
        "This LIKELY means you're missing Kubernetes Permissions, you can"
        ' validate this by checking if the error references permission problems'
        ' such as `requires one of ["container.*"] permission(s)`. Follow our'
        ' readme:'
        ' https://github.com/google/xpk/blob/main/README.md#troubleshooting for'
        ' instructions on how to fix these permissions.'
    )
  return return_code


def set_pathways_job_on_cluster(args) -> int:
  """Add PathwaysJob command on server side and ask user to verify it is created.

  Args:
    args: user provided arguments for running the command.

  Returns:
    0 if successful and 1 otherwise.
  """
  command = (
      'kubectl apply --server-side -f'
      f' https://github.com/google/pathways-job/releases/download/{PATHWAYS_JOB_VERSION}/install.yaml'
  )
  task = f'Install PathwaysJob on {args.cluster}'
  return_code = run_command_with_updates_retry(command, task)

  if return_code != 0:
    xpk_print(f'{task} returned with ERROR {return_code}.\n')
    xpk_print(
        "This LIKELY means you're missing Kubernetes Permissions, you can"
        ' validate this by checking if the error references permission problems'
        ' such as `requires one of ["container.*"] permission(s)`. Follow our'
        ' readme:'
        ' https://github.com/google/xpk/blob/main/README.md#troubleshooting for'
        ' instructions on how to fix these permissions.'
    )
  return return_code


def install_nccl_on_cluster(system: SystemCharacteristics) -> int:
  """Install NCCL plugin on the cluster.

  Args:
    system: system characteristics.

  Returns:
    0 if successful and 1 otherwise.
  """
  nccl_installer = (
      system.gpu_config.nccl_installer
      if system.gpu_config and system.gpu_config.nccl_installer
      else INSTALLER_NCCL_TCPXO
  )
  command = f'kubectl apply -f {nccl_installer}'

  return_code = run_command_with_updates(
      command, 'Install NCCL Plugin On Cluster'
  )

  if return_code != 0:
    xpk_print(
        f'Install NCCL Plugin On Cluster request returned ERROR {return_code}'
    )
    return 1

  return 0


def install_nri_on_cluster() -> int:
  """Install NRI Device Injector on the cluster.

  Args:
    system: system characteristics.

  Returns:
    0 if successful and 1 otherwise.
  """
  command = f'kubectl apply -f {NRI_DEVICE_INJECTOR}'
  return_code = run_command_with_updates(
      command, 'Install NRI Device Injector On Cluster'
  )

  if return_code != 0:
    xpk_print(
        'Install NRI Device Injector On Cluster request returned ERROR'
        f' {return_code}'
    )
    return 1

  return 0


def get_cluster_nodes_info() -> list[dict]:
  """Get list of cluster's nodes descrition in yaml format

  Returns:
    List of nodes info yaml objects.
  """
  xpk_print("Getting cluster's info...")
  command = 'kubectl get nodes -o yaml'
  err_code, val = run_command_for_value(
      command=command,
      task='Get cluster nodes info',
  )
  if err_code != 0:
    xpk_exit(err_code)
  data: dict[str, list[dict]] = yaml.safe_load(val)
  return data['items']


def count_nodes_on_cluster(system: SystemCharacteristics) -> int:
  """Count cluster nodes by accelerator type"""
  nodes_info = get_cluster_nodes_info()
  accelerators = [
      node['metadata']['labels']['cloud.google.com/gke-accelerator']
      for node in nodes_info
      if 'cloud.google.com/gke-accelerator' in node['metadata']['labels']
  ]
  if system.device_type != H200_DEVICE_TYPE:
    xpk_print(
        'Automatic node detection is not supported for device type:'
        f' {system.device_type}'
    )
    xpk_exit(1)
  num_nodes: int = sum(acc == system.gke_accelerator for acc in accelerators)
  return num_nodes


def get_cluster_network(args) -> str:
  xpk_print("Getting cluster's VPC network...")
  cluster_network_cmd = (
      'gcloud container clusters describe'
      f' {args.cluster} --location={get_cluster_location(args.project, args.cluster, args.zone)} --project={args.project} --format="value(network)"'
  )
  err_code, val = run_command_for_value(
      command=cluster_network_cmd,
      task='Get network cluster is in',
  )
  if err_code != 0:
    xpk_exit(err_code)
  return val.strip()


def update_cluster_with_gcpfilestore_driver_if_necessary(args) -> int:
  """Updates a GKE cluster to enable GCPFilestore CSI driver, if not enabled already.
  Args:
    args: user provided arguments for running the command.
  Returns:
    0 if successful and error code otherwise.
  """

  if is_driver_enabled_on_cluster(args, driver='gcpFilestoreCsiDriver'):
    return 0
  cluster_update_return_code = update_gke_cluster_with_addon(
      args, 'GcpFilestoreCsiDriver'
  )
  if cluster_update_return_code > 0:
    xpk_print('Updating GKE cluster to enable GCPFilestore CSI driver failed!')
    return cluster_update_return_code

  return 0


def update_cluster_with_parallelstore_driver_if_necessary(args) -> int:
  """Updates a GKE cluster to enable Parallelstore CSI driver, if not enabled already.
  Args:
    args: user provided arguments for running the command.
  Returns:
    0 if successful and error code otherwise.
  """
  if is_driver_enabled_on_cluster(args, driver='parallelstoreCsiDriver'):
    return 0
  cluster_update_return_code = update_gke_cluster_with_addon(
      args, 'ParallelstoreCsiDriver'
  )
  if cluster_update_return_code > 0:
    xpk_print('Updating GKE cluster to enable Parallelstore CSI driver failed!')
    return cluster_update_return_code

  return 0


def update_cluster_with_pd_driver_if_necessary(args) -> int:
  """Updates a GKE cluster to enable PersistentDisk CSI driver, if not enabled already.
  Args:
    args: user provided arguments for running the command.
  Returns:
    0 if successful and error code otherwise.
  """
  if is_driver_enabled_on_cluster(args, driver='gcePersistentDiskCsiDriver'):
    return 0
  cluster_update_return_code = update_gke_cluster_with_addon(
      args, 'GcePersistentDiskCsiDriver'
  )
  if cluster_update_return_code > 0:
    xpk_print(
        'Updating GKE cluster to enable PersistentDisk CSI driver failed!'
    )
    return cluster_update_return_code

  return 0


def update_cluster_with_lustre_driver_if_necessary(args) -> int:
  """Updates a GKE cluster to enable Lustre CSI driver, if not enabled already.
  Args:
    args: user provided arguments for running the command.
  Returns:
    0 if successful and error code otherwise.
  """
  if is_driver_enabled_on_cluster(args, driver='lustreCsiDriver') and (
      not args.enable_legacy_lustre_port
      or is_driver_enabled_on_cluster(
          args, driver='lustreCsiDriver', config_key='enableLegacyLustrePort'
      )
  ):
    return 0
  cluster_update_return_code = update_gke_cluster_with_lustre_driver_enabled(
      args
  )
  if cluster_update_return_code > 0:
    xpk_print(
        'Updating GKE cluster to enable PersistentDisk CSI driver failed!'
    )
    return cluster_update_return_code

  return 0


def is_driver_enabled_on_cluster(
    args, driver: str, config_key: str = 'enabled', config_val: str = 'true'
) -> bool:
  """Checks if the CSI driver is enabled on the cluster.
  Args:
    args: user provided arguments for running the command.
    driver (str) : name of the driver
    config (str): the config to look for; by default looks for "enabled" parameter
    config_val (str): the value indicating the enabled; default vale is "true"
  Returns:
    True if driver is enabled on the cluster and False otherwise.
  """
  command = (
      f'gcloud container clusters describe {args.cluster}'
      f' --project={args.project} --location={get_cluster_location(args.project, args.cluster, args.zone)}'
      f' --format="value(addonsConfig.{driver}Config.{config_key})"'
  )
  return_code, driver_enabled = run_command_for_value(
      command,
      f"Checks if {driver} driver's {config_key} is enabled in cluster"
      ' describe.',
  )
  if return_code != 0:
    xpk_exit(return_code)
  if driver_enabled.strip().lower() == config_val.lower():
    xpk_print(
        f"{driver} driver's {config_key} config is {config_val} on the cluster."
    )
    return True
  return False


def update_gke_cluster_with_addon(args, addon: str) -> int:
  """Run the GKE cluster update command for existing cluster and enabling passed addon.
  Args:
    args: user provided arguments for running the command.
  Returns:
    0 if successful and 1 otherwise.
  """
  command = (
      'gcloud container clusters update'
      f' {args.cluster} --project={args.project} --location={get_cluster_location(args.project, args.cluster, args.zone)} --update-addons'
      f' {addon}=ENABLED --quiet'
  )
  xpk_print(f'Updating GKE cluster to enable {addon}, may take a while!')
  return_code = run_command_with_updates(
      command, f'GKE Cluster Update to enable {addon}'
  )
  if return_code != 0:
    xpk_print(f'GKE Cluster Update request returned ERROR {return_code}')
    return 1
  return 0


def get_all_clusters_programmatic(args) -> tuple[list[str], int]:
  """Gets all the clusters associated with the project / region.

  Args:
    args: user provided arguments for running the command.

  Returns:
    List of cluster names and 0 if successful and 1 otherwise.
  """
  command = (
      'gcloud container clusters list'
      f' --project={args.project} '
      f'--filter=location~"{zone_to_region(args.zone)}.*"'
      ' --format="csv[no-heading](name)"'
  )
  return_code, raw_cluster_output = run_command_for_value(
      command, 'Find if Cluster Exists'
  )
  if return_code != 0:
    xpk_print(f'Find if Cluster Exists returned ERROR {return_code}')
    return [], return_code

  return raw_cluster_output.splitlines(), 0


def project_id_to_project_number(project_id: str) -> str:
  client = resourcemanager_v3.ProjectsClient()
  request = resourcemanager_v3.GetProjectRequest()
  request.name = f'projects/{project_id}'
  try:
    response = client.get_project(request=request)
  except PermissionDenied as e:
    xpk_print(
        f"Couldn't translate project id: {project_id} to project number."
        f' Error: {e}'
    )
    xpk_exit(1)
  parts = response.name.split('/', 1)
  xpk_print(f'Project number for project: {project_id} is {parts[1]}')
  return str(parts[1])


def setup_k8s_env(args) -> k8s_client.ApiClient:
  if not getattr(args, 'kind_cluster', False):
    add_zone_and_project(args)
    get_cluster_credentials(args)
    args.project_number = (
        project_id_to_project_number(args.project)
        if not args.dry_run
        else abs(hash(args.project) % (10**12))  # 12 digit hash
    )

  config.load_kube_config()
  return k8s_client.ApiClient()


def get_gpu_type_from_cluster(args) -> str:
  system = get_cluster_system_characteristics(args)
  if not system is None:
    return system.device_type
  return ''


def setup_k8s_service_accounts() -> None:
  """
  Creates/sets up SAs and the roles for them
  """
  default_sa = 'default'

  create_xpk_k8s_service_account()

  role_name = create_pod_reader_role()
  create_role_binding(default_sa, role_name)
  create_role_binding(XPK_SA, role_name)


def create_xpk_k8s_service_account() -> None:
  k8s_core_client = k8s_client.CoreV1Api()
  sa = k8s_client.V1ServiceAccount(
      metadata=k8s_client.V1ObjectMeta(name=XPK_SA)
  )

  xpk_print(f'Creating a new service account: {XPK_SA}')
  try:
    k8s_core_client.create_namespaced_service_account(
        DEFAULT_NAMESPACE, sa, pretty=True
    )
    xpk_print(f'Created a new service account: {sa} successfully')
  except ApiException:
    xpk_print(
        f'Service account: {XPK_SA} already exists. Skipping its creation'
    )


def create_pod_reader_role() -> str:
  """
  Creates the 'pod-reader' Role in the default namespace.
  """
  k8s_rbac_client = k8s_client.RbacAuthorizationV1Api()
  role_name = 'pod-reader'

  role = k8s_client.V1Role(
      metadata=k8s_client.V1ObjectMeta(
          name=role_name, namespace=DEFAULT_NAMESPACE
      ),
      rules=[
          k8s_client.V1PolicyRule(
              api_groups=[''],
              resources=['pods', 'services'],
              verbs=['get', 'list', 'watch'],
          ),
          k8s_client.V1PolicyRule(
              api_groups=['batch'],
              resources=['jobs'],
              verbs=['get', 'list', 'watch'],
          ),
      ],
  )

  xpk_print(
      f'Attempting to create Role: {role_name} in namespace:'
      f' {DEFAULT_NAMESPACE}'
  )
  try:
    k8s_rbac_client.create_namespaced_role(DEFAULT_NAMESPACE, role, pretty=True)
    xpk_print(f'Successfully created Role: {role_name}')
    return role_name
  except ApiException as e:
    if e.status == 409:  # Conflict, meaning it already exists
      xpk_print(f'Role: {role_name} already exists. Skipping its creation.')
      return role_name
    else:
      xpk_print(f'Error creating Role {role_name}: {e}')
      xpk_exit(1)


def create_role_binding(sa: str, role_name: str) -> None:
  """
  Creates a RoleBinding to associate the Service Account
  with the Role in the default namespace.
  Assumes the Service Account and the Role already exist.
  """
  k8s_rbac_client = k8s_client.RbacAuthorizationV1Api()
  role_binding_name = f'{sa}-{role_name}-binding'

  role_binding = k8s_client.V1RoleBinding(
      metadata=k8s_client.V1ObjectMeta(
          name=role_binding_name, namespace=DEFAULT_NAMESPACE
      ),
      subjects=[
          k8s_client.RbacV1Subject(
              kind='ServiceAccount', name=sa, namespace=DEFAULT_NAMESPACE
          )
      ],
      role_ref=k8s_client.V1RoleRef(
          kind='Role', name=role_name, api_group='rbac.authorization.k8s.io'
      ),
  )

  xpk_print(
      f'Attempting to create RoleBinding: {role_binding_name} for Service'
      f' Account: {XPK_SA} to Role: {role_name} in namespace:'
      f' {DEFAULT_NAMESPACE}'
  )
  try:
    k8s_rbac_client.create_namespaced_role_binding(
        DEFAULT_NAMESPACE, role_binding, pretty=True
    )
    xpk_print(
        f'Successfully created RoleBinding: {role_binding_name} for {XPK_SA}'
    )
  except ApiException as e:
    if e.status == 409:  # Conflict, meaning it already exists
      xpk_print(
          f'RoleBinding: {role_binding_name} already exists. Skipping its'
          ' creation.'
      )
    else:
      xpk_print(f'Error creating RoleBinding {role_binding_name}: {e}')
      xpk_exit(1)


def update_gke_cluster_with_workload_identity_enabled(args) -> int:
  """Run the GKE cluster update command for existing cluster and enable Workload Identity Federation.
  Args:
    args: user provided arguments for running the command.
  Returns:
    0 if successful and 1 otherwise.
  """
  command = (
      'gcloud container clusters update'
      f' {args.cluster} --project={args.project} --location={get_cluster_location(args.project, args.cluster, args.zone)} --workload-pool={args.project}.svc.id.goog'
      ' --quiet'
  )
  xpk_print(
      'Updating GKE cluster to enable Workload Identity Federation, may take a'
      ' while!'
  )
  return_code = run_command_with_updates(
      command, 'GKE Cluster Update to enable Workload Identity Federation'
  )
  if return_code != 0:
    xpk_print(f'GKE Cluster Update request returned ERROR {return_code}')
    return 1
  return 0


def update_gke_cluster_with_gcsfuse_driver_enabled(args) -> int:
  """Run the GKE cluster update command for existing cluster and enable GCSFuse CSI driver.
  Args:
    args: user provided arguments for running the command.
  Returns:
    0 if successful and 1 otherwise.
  """
  command = (
      'gcloud container clusters update'
      f' {args.cluster} --project={args.project} --location={get_cluster_location(args.project, args.cluster, args.zone)} --update-addons'
      ' GcsFuseCsiDriver=ENABLED --quiet'
  )
  xpk_print(
      'Updating GKE cluster to enable GCSFuse CSI driver, may take a while!'
  )
  return_code = run_command_with_updates(
      command, 'GKE Cluster Update to enable GCSFuse CSI driver'
  )
  if return_code != 0:
    xpk_print(f'GKE Cluster Update request returned ERROR {return_code}')
    return 1
  return 0


def update_gke_cluster_with_lustre_driver_enabled(args) -> int:
  """Run the GKE cluster update command for existing cluster and enable Lustre CSI driver.
  Args:
    args: user provided arguments for running the command.
  Returns:
    0 if successful and 1 otherwise.
  """
  command = (
      'gcloud container clusters update'
      f' {args.cluster} --project={args.project} --location={get_cluster_location(args.project, args.cluster, args.zone)}'
      ' --quiet'
  )
  if args.enable_legacy_lustre_port:
    command += ' --enable-legacy-lustre-port'
  else:
    command += ' --update-addons=LustreCsiDriver=ENABLED'
  xpk_print(
      'Updating GKE cluster to enable Lustre CSI driver, may take a while!'
  )
  return_code = run_command_with_updates(
      command, 'GKE Cluster Update to enable Lustre CSI driver'
  )
  if return_code != 0:
    xpk_print(f'GKE Cluster Update request returned ERROR {return_code}')
    return 1
  return 0


def is_workload_identity_enabled_on_cluster(args) -> bool:
  """Checks if Workload Identity Federation is enabled on the cluster.
  Args:
    args: user provided arguments for running the command.
  Returns:
    True if Workload Identity Federation is enabled on the cluster and False otherwise.
  """
  command = (
      f'gcloud container clusters describe {args.cluster}'
      f' --project={args.project} --location={get_cluster_location(args.project, args.cluster, args.zone)}'
      ' --format="value(workloadIdentityConfig.workloadPool)"'
  )
  return_code, workload_pool = run_command_for_value(
      command,
      'Checks if Workload Identity Federation is enabled in cluster describe.',
  )
  if return_code != 0:
    xpk_exit(return_code)
  if workload_pool == f'{args.project}.svc.id.goog':
    xpk_print(
        'Workload Identity Federation is enabled on the cluster, no update'
        ' needed.'
    )
    return True
  return False


def is_gcsfuse_driver_enabled_on_cluster(args) -> bool:
  """Checks if GCSFuse CSI driver is enabled on the cluster.
  Args:
    args: user provided arguments for running the command.
  Returns:
    True if GCSFuse CSI driver is enabled on the cluster and False otherwise.
  """
  command = (
      f'gcloud container clusters describe {args.cluster}'
      f' --project={args.project} --location={get_cluster_location(args.project, args.cluster, args.zone)}'
      ' --format="value(addonsConfig.gcsFuseCsiDriverConfig.enabled)"'
  )
  return_code, gcsfuse_driver_enabled = run_command_for_value(
      command,
      'Checks if GCSFuse CSI driver is enabled in cluster describe.',
  )
  if return_code != 0:
    xpk_exit(return_code)
  if gcsfuse_driver_enabled.strip().lower() == 'true':
    xpk_print('GCSFuse CSI driver is enabled on the cluster, no update needed.')
    return True
  return False


def update_cluster_with_workload_identity_if_necessary(args) -> int:
  """Updates a GKE cluster to enable Workload Identity Federation, if not enabled already.
  Args:
    args: user provided arguments for running the command.
  Returns:
    0 if successful and error code otherwise.
  """

  if is_workload_identity_enabled_on_cluster(args):
    return 0
  cluster_update_return_code = (
      update_gke_cluster_with_workload_identity_enabled(args)
  )
  if cluster_update_return_code > 0:
    xpk_print(
        'Updating GKE cluster to enable Workload Identity Federation failed!'
    )
    return cluster_update_return_code

  return 0


def update_cluster_with_gcsfuse_driver_if_necessary(args) -> int:
  """Updates a GKE cluster to enable GCSFuse CSI driver, if not enabled already.
  Args:
    args: user provided arguments for running the command.
  Returns:
    0 if successful and error code otherwise.
  """

  if is_gcsfuse_driver_enabled_on_cluster(args):
    return 0
  cluster_update_return_code = update_gke_cluster_with_gcsfuse_driver_enabled(
      args
  )
  if cluster_update_return_code > 0:
    xpk_print('Updating GKE cluster to enable GCSFuse CSI driver failed!')
    return cluster_update_return_code

  return 0


def get_cluster_credentials(args) -> int:
  """Run cluster configuration command to set the kubectl config.

  Args:
    args: user provided arguments for running the command.

  Returns:
    0 if successful and 1 otherwise.
  """
  location = get_cluster_location(args.project, args.cluster, args.zone)

  return_code = _get_credentials(
      project=args.project,
      cluster=args.cluster,
      location=location,
      dns_endpoint=True,
  )

  if return_code != 0 or not _are_credentials_valid():
    xpk_print('Detected error. Retrying without --dns-endpoint flag...')
    return_code = _get_credentials(
        project=args.project,
        cluster=args.cluster,
        location=location,
        dns_endpoint=False,
    )
    if return_code != 0:
      return return_code

  xpk_print('Finished get-credentials and kubectl setup.')
  return 0


def _get_credentials(
    project: str, cluster: str, location: str, dns_endpoint: bool
) -> int:
  dns_endpoint_arg = '--dns-endpoint' if dns_endpoint else ''
  command = (
      'gcloud container clusters get-credentials'
      f' {cluster} --location={location} {dns_endpoint_arg}'
      f' --project={project} && kubectl config view && kubectl config'
      ' set-context --current --namespace=default'
  )
  task = f'get-credentials-dns-endpoint to cluster {cluster}'
  return run_command_with_updates(command, task, verbose=False)


def _are_credentials_valid() -> bool:
  kubectl_command = 'kubectl get pods'
  kubectl_return_code = run_command_with_updates(
      kubectl_command, 'Test kubectl credentials'
  )
  return kubectl_return_code == 0
