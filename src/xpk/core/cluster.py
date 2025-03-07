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

from google.api_core.exceptions import PermissionDenied
from google.cloud import resourcemanager_v3
from kubernetes import client as k8s_client
from kubernetes import config
from kubernetes.client.exceptions import ApiException

from ..utils.console import xpk_exit, xpk_print
from .capacity import CapacityManager, DeviceType
from .commands import (
    run_command_for_value,
    run_command_with_updates,
    run_command_with_updates_retry,
)
from .gcloud_context import GCloudContextManager, GKEVersionManager
from .nodepool import NodePoolManager
from .resources import ResourceManager
from .system_characteristics import SystemCharacteristics

JOBSET_VERSION = 'v0.7.2'
INSTALLER_NCC_TCPX = 'https://raw.githubusercontent.com/GoogleCloudPlatform/container-engine-accelerators/master/gpudirect-tcpx/nccl-tcpx-installer.yaml'
INSTALLER_NCC_TCPXO = 'https://raw.githubusercontent.com/GoogleCloudPlatform/container-engine-accelerators/master/gpudirect-tcpxo/nccl-tcpxo-installer.yaml'


class ClusterManager:
  """Manages Jobset and NCCL installation on Kubernetes clusters."""

  def __init__(self, args, system: SystemCharacteristics):
    self.args = args
    self.system = system

  # TODO(vbarr): Remove this function when jobsets gets enabled by default on
  # GKE clusters.
  def set_jobset_on_cluster(self) -> int:
    """Add jobset command on server side and ask user to verify it is created.

    Returns:
      0 if successful and 1 otherwise.
    """
    command = (
        'kubectl apply --server-side -f'
        f' https://github.com/kubernetes-sigs/jobset/releases/download/{JOBSET_VERSION}/manifests.yaml'
    )
    task = f'Install Jobset on {self.args.cluster}'
    return_code = run_command_with_updates_retry(command, task, self.args)

    if return_code != 0:
      xpk_print(f'{task} returned with ERROR {return_code}.\n')
      xpk_print(
          "This LIKELY means you're missing Kubernetes Permissions, you can"
          ' validate this by checking if the error references permission'
          ' problems such as `requires one of ["container.*"] permission(s)`.'
          ' Follow our readme:'
          ' https://github.com/google/xpk/blob/main/README.md#troubleshooting'
          ' for instructions on how to fix these permissions.'
      )
    return return_code

  def install_nccl_on_cluster(self) -> int:
    """Install NCCL plugin on the cluster.

    Returns:
      0 if successful and 1 otherwise.
    """
    if self.system.device_type == DeviceType.H100.value:
      command = f'kubectl apply -f {INSTALLER_NCC_TCPX}'
    else:
      command = f'kubectl apply -f {INSTALLER_NCC_TCPXO}'

    return_code = run_command_with_updates(
        command, 'Install NCCL Plugin On Cluster', self.args
    )

    if return_code != 0:
      xpk_print(
          f'Install NCCL Plugin On Cluster request returned ERROR {return_code}'
      )
      return 1

    return 0

  def get_cluster_network(self) -> str:
    xpk_print("Getting cluster's VPC network...")
    cluster_network_cmd = (
        'gcloud container clusters describe'
        f' {self.args.cluster} --zone={GCloudContextManager.zone_to_region(self.args.zone)} --project={self.args.project} --format="value(network)"'
    )
    err_code, val = run_command_for_value(
        command=cluster_network_cmd,
        task='Get network cluster is in',
        global_args=self.args,
    )
    if err_code != 0:
      xpk_exit(err_code)
    return val.strip()

  def update_cluster_with_gcpfilestore_driver_if_necessary(self) -> int:
    """Updates a GKE cluster to enable GCPFilestore CSI driver, if not enabled already.
    Args:
      args: user provided arguments for running the command.
    Returns:
      0 if successful and error code otherwise.
    """

    if self.is_driver_enabled_on_cluster(driver='gcpFilestoreCsiDriver'):
      return 0
    cluster_update_return_code = self.update_gke_cluster_with_addon(
        'GcpFilestoreCsiDriver'
    )
    if cluster_update_return_code > 0:
      xpk_print(
          'Updating GKE cluster to enable GCPFilestore CSI driver failed!'
      )
      return cluster_update_return_code

    return 0

  def is_driver_enabled_on_cluster(self, driver: str) -> bool:
    """Checks if GCSFuse CSI driver is enabled on the cluster.
    Args:
      args: user provided arguments for running the command.
      driver (str) : name of the driver
    Returns:
      True if driver is enabled on the cluster and False otherwise.
    """
    command = (
        f'gcloud container clusters describe {self.args.cluster}'
        f' --project={self.args.project} --region={GCloudContextManager.zone_to_region(self.args.zone)}'
        f' --format="value(addonsConfig.{driver}Config.enabled)"'
    )
    return_code, gcsfuse_driver_enabled = run_command_for_value(
        command,
        f'Checks if {driver} driver is enabled in cluster describe.',
        self.args,
    )
    if return_code != 0:
      xpk_exit(return_code)
    if gcsfuse_driver_enabled.lower() == 'true':
      xpk_print(f'{driver} driver is enabled on the cluster, no update needed.')
      return True
    return False

  def update_gke_cluster_with_addon(self, addon: str) -> int:
    """Run the GKE cluster update command for existing cluster and enabling passed addon.
    Args:
      args: user provided arguments for running the command.
    Returns:
      0 if successful and 1 otherwise.
    """
    command = (
        'gcloud container clusters update'
        f' {self.args.cluster} --project={self.args.project}'
        f' --region={GCloudContextManager.zone_to_region(self.args.zone)}'
        f' --update-addons {addon}=ENABLED'
        ' --quiet'
    )
    xpk_print(f'Updating GKE cluster to enable {addon}, may take a while!')
    return_code = run_command_with_updates(
        command, f'GKE Cluster Update to enable {addon}', self.args
    )
    if return_code != 0:
      xpk_print(f'GKE Cluster Update request returned ERROR {return_code}')
      return 1
    return 0

  def get_all_clusters_programmatic(self) -> tuple[list[str], int]:
    """Gets all the clusters associated with the project / region.

    Args:
      args: user provided arguments for running the command.

    Returns:
      List of cluster names and 0 if successful and 1 otherwise.
    """
    region = GCloudContextManager.zone_to_region(self.args.zone)
    command = (
        'gcloud container clusters list'
        f' --project={self.args.project} --region={region}'
        ' --format="csv[no-heading](name)"'
    )
    return_code, raw_cluster_output = run_command_for_value(
        command, 'Find if Cluster Exists', self.args
    )
    if return_code != 0:
      xpk_print(f'Find if Cluster Exists returned ERROR {return_code}')
      return [], return_code

    return raw_cluster_output.splitlines(), 0

  def project_id_to_project_number(self, project_id: str) -> str:
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

  def setup_k8s_env(self) -> k8s_client.ApiClient:
    if not getattr(self.args, 'kind_cluster', False):
      GCloudContextManager.add_zone_and_project(self.args)
      self.get_cluster_credentials()
      self.args.project_number = self.project_id_to_project_number(
          self.args.project
      )

    config.load_kube_config()
    return k8s_client.ApiClient()  # pytype: disable=bad-return-type

  def create_k8s_service_account(self, name: str, namespace: str) -> None:
    k8s_core_client = k8s_client.CoreV1Api()
    sa = k8s_client.V1ServiceAccount(
        metadata=k8s_client.V1ObjectMeta(name=name)
    )

    xpk_print(f'Creating a new service account: {name}')
    try:
      k8s_core_client.create_namespaced_service_account(
          namespace, sa, pretty=True
      )
      xpk_print(f'Created a new service account: {sa} successfully')
    except ApiException:
      xpk_print(
          f'Service account: {name} already exists. Skipping its creation'
      )

  def update_gke_cluster_with_clouddns(self) -> int:
    """Run the GKE cluster update command for existing clusters and enable CloudDNS.

    Args:
      args: user provided arguments for running the command.

    Returns:
      0 if successful and 1 otherwise.
    """
    command = (
        'gcloud container clusters update'
        f' {self.args.cluster} --project={self.args.project}'
        f' --region={GCloudContextManager.zone_to_region(self.args.zone)}'
        ' --cluster-dns=clouddns'
        ' --cluster-dns-scope=vpc'
        f' --cluster-dns-domain={self.args.cluster}-domain'
        ' --quiet'
    )
    xpk_print('Updating GKE cluster to use Cloud DNS, may take a while!')
    return_code = run_command_with_updates(
        command, 'GKE Cluster Update to enable Cloud DNS', self.args
    )
    if return_code != 0:
      xpk_print(f'GKE Cluster Update request returned ERROR {return_code}')
      return 1
    return 0

  def update_gke_cluster_with_workload_identity_enabled(self) -> int:
    """Run the GKE cluster update command for existing cluster and enable Workload Identity Federation.
    Args:
      args: user provided arguments for running the command.
    Returns:
      0 if successful and 1 otherwise.
    """
    command = (
        'gcloud container clusters update'
        f' {self.args.cluster} --project={self.args.project}'
        f' --region={GCloudContextManager.zone_to_region(self.args.zone)}'
        f' --workload-pool={self.args.project}.svc.id.goog'
        ' --quiet'
    )
    xpk_print(
        'Updating GKE cluster to enable Workload Identity Federation, may take'
        ' a while!'
    )
    return_code = run_command_with_updates(
        command,
        'GKE Cluster Update to enable Workload Identity Federation',
        self.args,
    )
    if return_code != 0:
      xpk_print(f'GKE Cluster Update request returned ERROR {return_code}')
      return 1
    return 0

  def update_gke_cluster_with_gcsfuse_driver_enabled(self) -> int:
    """Run the GKE cluster update command for existing cluster and enable GCSFuse CSI driver.
    Args:
      args: user provided arguments for running the command.
    Returns:
      0 if successful and 1 otherwise.
    """
    command = (
        'gcloud container clusters update'
        f' {self.args.cluster} --project={self.args.project}'
        f' --region={GCloudContextManager.zone_to_region(self.args.zone)}'
        ' --update-addons GcsFuseCsiDriver=ENABLED'
        ' --quiet'
    )
    xpk_print(
        'Updating GKE cluster to enable GCSFuse CSI driver, may take a while!'
    )
    return_code = run_command_with_updates(
        command, 'GKE Cluster Update to enable GCSFuse CSI driver', self.args
    )
    if return_code != 0:
      xpk_print(f'GKE Cluster Update request returned ERROR {return_code}')
      return 1
    return 0

  def upgrade_gke_control_plane_version(self, default_rapid_gke_version) -> int:
    """Upgrade GKE cluster's control plane version before updating nodepools to use CloudDNS.

    Args:
      args: user provided arguments for running the command.
      default_rapid_gke_version: Rapid default version for the upgrade.

    Returns:
      0 if successful and 1 otherwise.
    """
    command = (
        'gcloud container clusters upgrade'
        f' {self.args.cluster} --project={self.args.project}'
        f' --region={GCloudContextManager.zone_to_region(self.args.zone)}'
        f' --cluster-version={default_rapid_gke_version}'
        ' --master'
        ' --quiet'
    )
    xpk_print("Updating GKE cluster's control plane version, may take a while!")
    return_code = run_command_with_updates(
        command,
        'GKE Cluster control plane version update to enable Cloud DNS',
        self.args,
    )
    if return_code != 0:
      xpk_print(
          "GKE cluster's control plane version update request returned"
          f' ERROR {return_code}'
      )
      return 1
    return 0

  def is_cluster_using_clouddns(self) -> bool:
    """Checks if cluster is using CloudDNS.
    Args:
      args: user provided arguments for running the command.

    Returns:
      True if cluster is using CloudDNS and False otherwise.
    """
    command = (
        'gcloud container clusters describe'
        f' {self.args.cluster} --project={self.args.project} --region={GCloudContextManager.zone_to_region(self.args.zone)} 2>'
        ' /dev/null | grep "clusterDns: CLOUD_DNS"'
    )
    return_code, _ = run_command_for_value(
        command,
        'Check if Cloud DNS is enabled in cluster describe.',
        self.args,
    )
    if return_code == 0:
      xpk_print('Cloud DNS is enabled on the cluster, no update needed.')
      return True
    return False

  def is_workload_identity_enabled_on_cluster(self) -> bool:
    """Checks if Workload Identity Federation is enabled on the cluster.
    Args:
      args: user provided arguments for running the command.
    Returns:
      True if Workload Identity Federation is enabled on the cluster and False otherwise.
    """
    command = (
        f'gcloud container clusters describe {self.args.cluster}'
        f' --project={self.args.project} --region={GCloudContextManager.zone_to_region(self.args.zone)}'
        ' --format="value(workloadIdentityConfig.workloadPool)"'
    )
    return_code, workload_pool = run_command_for_value(
        command,
        'Checks if Workload Identity Federation is enabled in cluster'
        ' describe.',
        self.args,
    )
    if return_code != 0:
      xpk_exit(return_code)
    if workload_pool == f'{self.args.project}.svc.id.goog':
      xpk_print(
          'Workload Identity Federation is enabled on the cluster, no update'
          ' needed.'
      )
      return True
    return False

  def is_gcsfuse_driver_enabled_on_cluster(self) -> bool:
    """Checks if GCSFuse CSI driver is enabled on the cluster.
    Args:
      args: user provided arguments for running the command.
    Returns:
      True if GCSFuse CSI driver is enabled on the cluster and False otherwise.
    """
    command = (
        f'gcloud container clusters describe {self.args.cluster}'
        f' --project={self.args.project} --region={GCloudContextManager.zone_to_region(self.args.zone)}'
        ' --format="value(addonsConfig.gcsFuseCsiDriverConfig.enabled)"'
    )
    return_code, gcsfuse_driver_enabled = run_command_for_value(
        command,
        'Checks if GCSFuse CSI driver is enabled in cluster describe.',
        self.args,
    )
    if return_code != 0:
      xpk_exit(return_code)
    if gcsfuse_driver_enabled.lower() == 'true':
      xpk_print(
          'GCSFuse CSI driver is enabled on the cluster, no update needed.'
      )
      return True
    return False

  def update_cluster_with_clouddns_if_necessary(self) -> int:
    """Updates a GKE cluster to use CloudDNS, if not enabled already.

    Args:
      args: user provided arguments for running the command.

    Returns:
      0 if successful and error code otherwise.
    """
    all_clusters, return_code = self.get_all_clusters_programmatic()
    if return_code > 0:
      xpk_print('Listing all clusters failed!')
      return 1
    if self.args.cluster in all_clusters:
      # If cluster is already using clouddns, no update necessary!
      if self.is_cluster_using_clouddns():
        return 0
      cluster_update_return_code = self.update_gke_cluster_with_clouddns()
      if cluster_update_return_code > 0:
        xpk_print('Updating GKE cluster to use CloudDNS failed!')
        return cluster_update_return_code

      # Find default rapid control plane version and update the control plane to the same.
      gke_version_manager = GKEVersionManager(self.args)
      upgrade_master_return_code = self.upgrade_gke_control_plane_version(
          gke_version_manager.default_rapid_gke_version,  # pytype: disable=attribute-error
      )
      if upgrade_master_return_code > 0:
        xpk_print("Updating GKE cluster's control plane upgrade failed!")
        return upgrade_master_return_code

      # Upgrade nodepools version after the master upgrade.
      capacity_manager = CapacityManager(self.args)
      resource_manager = ResourceManager(
          self.args, capacity_manager, self.system
      )
      nodepool_manager = NodePoolManager(
          self.args, self.system, resource_manager, capacity_manager
      )
      node_pool_update_code = nodepool_manager.upgrade_gke_nodepools_version(
          gke_version_manager.default_rapid_gke_version,  # pytype: disable=attribute-error
      )
      if node_pool_update_code > 0:
        xpk_print('Upgrading nodepools version failed!')
        return node_pool_update_code
    return 0

  def update_cluster_with_workload_identity_if_necessary(self) -> int:
    """Updates a GKE cluster to enable Workload Identity Federation, if not enabled already.
    Args:
      args: user provided arguments for running the command.
    Returns:
      0 if successful and error code otherwise.
    """

    if self.is_workload_identity_enabled_on_cluster():
      return 0
    cluster_update_return_code = (
        self.update_gke_cluster_with_workload_identity_enabled()
    )
    if cluster_update_return_code > 0:
      xpk_print(
          'Updating GKE cluster to enable Workload Identity Federation failed!'
      )
      return cluster_update_return_code

    return 0

  def update_cluster_with_gcsfuse_driver_if_necessary(self) -> int:
    """Updates a GKE cluster to enable GCSFuse CSI driver, if not enabled already.
    Args:
      args: user provided arguments for running the command.
    Returns:
      0 if successful and error code otherwise.
    """

    if self.is_gcsfuse_driver_enabled_on_cluster():
      return 0
    cluster_update_return_code = (
        self.update_gke_cluster_with_gcsfuse_driver_enabled()
    )
    if cluster_update_return_code > 0:
      xpk_print('Updating GKE cluster to enable GCSFuse CSI driver failed!')
      return cluster_update_return_code

    return 0

  def get_cluster_credentials(self) -> None:
    """Run cluster configuration command to set the kubectl config.

    Args:
      args: user provided arguments for running the command.

    Returns:
      0 if successful and 1 otherwise.
    """
    command = (
        'gcloud container clusters get-credentials'
        f' {self.args.cluster} --region={GCloudContextManager.zone_to_region(self.args.zone)} --project={self.args.project} &&'
        ' kubectl config view && kubectl config set-context --current'
        ' --namespace=default'
    )
    task = f'get-credentials to cluster {self.args.cluster}'
    return_code = run_command_with_updates_retry(
        command, task, self.args, verbose=False
    )
    if return_code != 0:
      xpk_print(f'{task} returned ERROR {return_code}')
      xpk_exit(return_code)
