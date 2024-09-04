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

from ..core.commands import (
    run_command_for_value,
    run_command_with_updates,
    run_command_with_updates_retry,
)
from ..core.core import (
    VERTEX_TENSORBOARD_FEATURE_FLAG,
    add_zone_and_project,
    create_cluster_configmaps,
    create_cluster_network_config,
    create_vertex_tensorboard,
    delete_cluster_subnets,
    get_all_clusters_programmatic,
    get_gke_control_plane_version,
    get_gke_node_pool_version,
    get_gke_server_config,
    h100_device_type,
    install_nccl_on_cluster,
    run_gke_node_pool_create_command,
    set_jobset_on_cluster,
    set_up_cluster_network_for_gpu,
    update_cluster_with_clouddns_if_necessary,
    update_cluster_with_workload_identity_if_necessary,
    update_cluster_with_gcsfuse_driver_if_necessary,
    zone_to_region,
)
from ..core.kueue import (
    cluster_preheat_yml,
    enable_kueue_credentials,
    install_kueue_on_cluster,
)
from ..core.nap import enable_autoprovisioning_on_cluster
from ..core.system_characteristics import (
    AcceleratorType,
    AcceleratorTypeToAcceleratorCharacteristics,
    SystemCharacteristics,
    get_system_characteristics,
)
from ..utils import write_tmp_file, xpk_exit, xpk_print


def cluster_create(args) -> None:
  """Function around cluster creation.

  Args:
    args: user provided arguments for running the command.

  Returns:
    0 if successful and 1 otherwise.
  """
  system, return_code = get_system_characteristics(args)

  if return_code > 0:
    xpk_print('Fetching system characteristics failed!')
    xpk_exit(return_code)

  xpk_print(f'Starting cluster create for cluster {args.cluster}:', flush=True)
  add_zone_and_project(args)

  return_code, gke_server_config = get_gke_server_config(args)
  if return_code != 0:
    xpk_exit(return_code)

  return_code, gke_control_plane_version = get_gke_control_plane_version(
      args, gke_server_config
  )
  if return_code != 0:
    xpk_exit(return_code)

  create_cluster_command_code = create_cluster_if_necessary(
      args, gke_control_plane_version, system
  )
  if create_cluster_command_code != 0:
    xpk_exit(create_cluster_command_code)

  # Enable WorkloadIdentity if not enabled already.
  if args.enable_workload_identity or args.enable_gcsfuse_csi_driver:
    update_cluster_command_code = (
        update_cluster_with_workload_identity_if_necessary(args)
    )
    if update_cluster_command_code != 0:
      xpk_exit(update_cluster_command_code)

  # Enable GCSFuse CSI Driver if not enabled already.
  if args.enable_gcsfuse_csi_driver:
    update_cluster_command_code = (
        update_cluster_with_gcsfuse_driver_if_necessary(args)
    )
    if update_cluster_command_code != 0:
      xpk_exit(update_cluster_command_code)

  # Update Pathways clusters with CloudDNS if not enabled already.
  if args.enable_pathways:
    update_cluster_command_code = update_cluster_with_clouddns_if_necessary(
        args
    )
    if update_cluster_command_code != 0:
      xpk_exit(update_cluster_command_code)

  set_cluster_command_code = set_cluster_command(args)
  if set_cluster_command_code != 0:
    xpk_exit(set_cluster_command_code)

  # create Vertex Tensorboard for new and existing clusters if create-vertex-tensorboard is set
  tensorboard_config = {}
  if VERTEX_TENSORBOARD_FEATURE_FLAG and args.create_vertex_tensorboard:
    tensorboard_config = create_vertex_tensorboard(args)
    # exit if failed to create Tensorboard in Vertex AI
    if not tensorboard_config:
      xpk_exit(1)

  if system.accelerator_type == AcceleratorType['GPU']:
    xpk_print('Setting up Network for cluster')
    set_up_cluster_network_code = set_up_cluster_network_for_gpu(args, system)
    if set_up_cluster_network_code != 0:
      xpk_exit(set_up_cluster_network_code)

  if system.device_type == h100_device_type:
    xpk_print('Creating Network Config for cluster')
    create_cluster_network_config_code = create_cluster_network_config(args)
    if create_cluster_network_config_code != 0:
      xpk_exit(create_cluster_network_config_code)

  # Check the control plane version of the cluster and determine the node pool
  # version to use.
  return_code, gke_node_pool_version = get_gke_node_pool_version(
      args, gke_server_config
  )
  if return_code != 0:
    xpk_exit(return_code)

  run_gke_node_pool_create_command_code = run_gke_node_pool_create_command(
      args, system, gke_node_pool_version
  )
  if run_gke_node_pool_create_command_code != 0:
    xpk_exit(run_gke_node_pool_create_command_code)

  xpk_print(
      'Enabling the jobset API on our cluster, to be deprecated when Jobset is'
      ' globally available'
  )
  set_jobset_on_cluster_code = set_jobset_on_cluster(args)
  if set_jobset_on_cluster_code != 0:
    xpk_exit(set_jobset_on_cluster_code)

  xpk_print('Enabling Kueue on the cluster')
  install_kueue_on_cluster_code = install_kueue_on_cluster(args)
  if install_kueue_on_cluster_code != 0:
    xpk_exit(install_kueue_on_cluster_code)

  # Provision node pools dynamically based on incoming workloads:
  # Currently autoprovisioning is not supported with Pathways.
  autoprovisioning_config = None
  if not args.enable_pathways and args.enable_autoprovisioning:
    xpk_print('Enabling Autoprovisioning')
    autoprovisioning_config, return_code = enable_autoprovisioning_on_cluster(
        args, system
    )
    if return_code != 0:
      xpk_exit(return_code)

  xpk_print('Enable Kueue Credentials')
  enable_kueue_credentials_code = enable_kueue_credentials(
      args, system, autoprovisioning_config
  )
  if enable_kueue_credentials_code != 0:
    xpk_exit(enable_kueue_credentials_code)

  if system.accelerator_type == AcceleratorType['GPU']:
    xpk_print('Installing NCCL Plugin for cluster')
    install_nccl_code = install_nccl_on_cluster(args, system)
    if install_nccl_code != 0:
      xpk_exit(install_nccl_code)

  xpk_print('Creating ConfigMap for cluster')
  create_cluster_configmaps_code = create_cluster_configmaps(
      args, system, tensorboard_config, autoprovisioning_config
  )
  if create_cluster_configmaps_code != 0:
    xpk_exit(create_cluster_configmaps_code)

  xpk_print('GKE commands done! Resources are created.')
  xpk_print(
      'See your GKE Cluster here:'
      # pylint: disable=line-too-long
      f' https://console.cloud.google.com/kubernetes/clusters/details/{zone_to_region(args.zone)}/{args.cluster}/details?project={args.project}'
  )
  xpk_exit(0)


def cluster_delete(args) -> None:
  """Function around cluster delete.

  Args:
    args: user provided arguments for running the command.

  Returns:
    0 if successful and 1 otherwise.
  """
  xpk_print(f'Starting cluster delete for cluster: {args.cluster}', flush=True)
  add_zone_and_project(args)
  run_gke_cluster_delete_command_code = run_gke_cluster_delete_command(args)
  if run_gke_cluster_delete_command_code != 0:
    xpk_exit(run_gke_cluster_delete_command_code)
  xpk_print(f'GKE commands done! Cluster {args.cluster} deleted.\n')
  xpk_exit(0)


def cluster_cacheimage(args) -> None:
  """Function around cluster cacheimage.

  Args:
    args: user provided arguments for running the command.

  Returns:
    0 if successful and 1 otherwise.
  """
  xpk_print(
      f'Starting cluster cacheimage for cluster: {args.cluster}', flush=True
  )
  add_zone_and_project(args)

  set_cluster_command_code = set_cluster_command(args)
  if set_cluster_command_code != 0:
    xpk_exit(set_cluster_command_code)
  system, return_code = get_system_characteristics(args)

  if return_code > 0:
    xpk_print('Fetching system characteristics failed!')
    xpk_exit(return_code)

  node_selector_key = AcceleratorTypeToAcceleratorCharacteristics[
      system.accelerator_type
  ].accelerator_label
  yml_string = cluster_preheat_yml.format(
      cachekey=args.cache_key,
      image_name=args.docker_image,
      nodeSelectorKey=node_selector_key,
  )
  tmp = write_tmp_file(yml_string)
  command_apply = f'kubectl apply -f {str(tmp.file.name)}'
  command_delete = (
      f'kubectl delete -f {str(tmp.file.name)} --ignore-not-found=true'
  )

  return_code = run_command_with_updates(
      command_delete, 'Deleting Cached Image', args
  )
  if return_code != 0:
    xpk_print(f'Delete Cached Image returned ERROR {return_code}')
    xpk_exit(return_code)

  return_code = run_command_with_updates(
      command_apply, 'Creating Cached Image', args
  )
  if return_code != 0:
    xpk_print(f'Create Cached Image returned ERROR {return_code}')
    xpk_exit(return_code)
  xpk_exit(0)


def cluster_describe(args) -> None:
  """Function around cluster describe.

  Args:
    args: user provided arguments for running the command.

  Returns:
    0 if successful and 1 otherwise.
  """
  xpk_print(f'Starting nodepool list for cluster: {args.cluster}', flush=True)
  add_zone_and_project(args)

  set_cluster_command_code = set_cluster_command(args)
  if set_cluster_command_code != 0:
    xpk_exit(set_cluster_command_code)

  command = (
      f'gcloud container node-pools  list --cluster {args.cluster} '
      f'--project={args.project} --region={zone_to_region(args.zone)}'
  )

  return_code = run_command_with_updates(command, 'Cluster nodepool list', args)
  if return_code != 0:
    xpk_exit(return_code)

  return_code_node_output, node_output = run_command_for_value(
      r'kubectl get node --no-headers=true'
      r" --selector='cloud.google.com/gke-tpu-accelerator' | wc -l",
      'Count TPU Nodes',
      args,
  )
  if return_code_node_output != 0:
    xpk_exit(return_code_node_output)
  number_tpu_vms_in_cluster = int(node_output)

  return_code_pod_output, pod_output = run_command_for_value(
      "kubectl get pod -o=custom-columns='Status:.status.phase' | grep -i"
      ' Running | wc -l',
      'Count TPU Pods',
      args,
  )
  if return_code_pod_output != 0:
    xpk_exit(return_code_pod_output)
  number_tpu_pods_in_cluster = int(pod_output)

  xpk_print(
      f'The cluster contains {number_tpu_vms_in_cluster} TPUVMs of which'
      f' {number_tpu_pods_in_cluster} are in use.'
  )

  xpk_print('GKE commands done!\n')
  xpk_exit(0)


def cluster_list(args) -> None:
  """Function around cluster list.

  Args:
    args: user provided arguments for running the command.

  Returns:
    0 if successful and 1 otherwise.
  """
  add_zone_and_project(args)
  xpk_print(f'For project {args.project} and zone {args.zone}:', flush=True)
  if run_gke_clusters_list_command(args):
    xpk_exit(1)
  xpk_exit(0)


def cluster_create_pathways(args) -> None:
  """Function around cluster creation for Pathways.

  Args:
    args: user provided arguments for running the command.

  Returns:
    0 if successful and 1 otherwise.
  """
  args.enable_pathways = True
  cluster_create(args)


def create_cluster_if_necessary(
    args, gke_control_plane_version: str, system: SystemCharacteristics
) -> int:
  """Creates cluster if not present in the project.

  Args:
    args: user provided arguments for running the command.
    gke_control_plane_version: version used if creating the cluster.
    system: system characteristics.

  Returns:
    0 if successful and 1 otherwise.
  """
  all_clusters, return_code = get_all_clusters_programmatic(args)
  if return_code > 0:
    xpk_print('Listing all clusters failed!')
    return 1
  if args.cluster in all_clusters:
    xpk_print('Skipping cluster creation since it already exists.')
    return 0
  else:
    return run_gke_cluster_create_command(
        args, gke_control_plane_version, system
    )


def run_gke_cluster_delete_command(args) -> int:
  """Run the Delete GKE Cluster request.

  Args:
    args: user provided arguments for running the command.

  Returns:
    0 if successful and 1 otherwise.
  """
  command = (
      'gcloud beta container clusters delete'
      f' {args.cluster} --project={args.project}'
      f' --region={zone_to_region(args.zone)} --quiet'
  )

  return_code = run_command_with_updates(command, 'Cluster Delete', args)
  if return_code != 0:
    xpk_print(f'Cluster delete request returned ERROR {return_code}')
    return 1

  return_code = delete_cluster_subnets(args)
  if return_code != 0:
    return return_code

  return 0


def run_gke_clusters_list_command(args) -> int:
  """List GKE Clusters within the project and location.

  Args:
    args: user provided arguments for running the command.

  Returns:
    0 if successful and 1 otherwise.
  """
  command = (
      'gcloud container clusters list'
      f' --project={args.project} --region={zone_to_region(args.zone)}'
  )
  return_code = run_command_with_updates(command, 'Cluster List', args)
  if return_code != 0:
    xpk_print(f'Cluster list request returned ERROR {return_code}')
    return 1

  return 0


def run_gke_cluster_create_command(
    args, gke_control_plane_version: str, system: SystemCharacteristics
) -> int:
  """Run the Create GKE Cluster request.

  Args:
    args: user provided arguments for running the command.
    gke_control_plane_version: version used if creating the cluster.
    system: system characteristics.

  Returns:
    0 if successful and 1 otherwise.
  """
  machine_type = args.default_pool_cpu_machine_type
  if args.cluster_cpu_machine_type != '':
    xpk_print(
        'Warning: Note that cluster-cpu-machine-type is soon to be',
        ' deprecated. Please use --default-pool-cpu-machine-type instead,'
        ' to denote the machine type of the default cpu node pool. Set'
        ' the machine type of other cpu nodepools using `--device-type`.',
    )
    machine_type = args.cluster_cpu_machine_type

  # Create the regional cluster with `num-nodes` CPU nodes in the same zone as
  # TPUs. This has been tested with clusters of 300 VMs. Larger clusters will
  # benefit from a larger initial `--num-nodes`. After the cluster is created,
  # the auto-scaler can reduce/increase the nodes based on the load.

  command = (
      'gcloud beta container clusters create'
      f' {args.cluster} --project={args.project}'
      f' --region={zone_to_region(args.zone)}'
      f' --node-locations={args.zone}'
      f' --cluster-version={gke_control_plane_version}'
      f' --machine-type={machine_type}'
      ' --enable-autoscaling'
      ' --total-min-nodes 1 --total-max-nodes 1000'
      f' --num-nodes {args.default_pool_cpu_num_nodes}'
      f' {args.custom_cluster_arguments}'
      ' --release-channel rapid'
  )

  if system.accelerator_type == AcceleratorType['GPU']:
    command += (
        ' --enable-dataplane-v2 --enable-ip-alias'
        ' --enable-multi-networking --no-enable-autoupgrade'
    )
  else:
    command += ' --location-policy=BALANCED --scopes=storage-full,gke-default'

    if args.enable_pathways:
      command += (
          ' --enable-ip-alias'
          f' --create-subnetwork name={args.cluster}-subnetwork'
          ' --cluster-dns=clouddns'
          ' --cluster-dns-scope=vpc'
          f' --cluster-dns-domain={args.cluster}-domain'
      )

  if args.enable_workload_identity or args.enable_gcsfuse_csi_driver:
    command += f' --workload-pool={args.project}.svc.id.goog'

  if args.enable_gcsfuse_csi_driver:
    command += ' --addons GcsFuseCsiDriver'

  return_code = run_command_with_updates(command, 'GKE Cluster Create', args)
  if return_code != 0:
    xpk_print(f'GKE Cluster Create request returned ERROR {return_code}')
    return 1
  return 0


def set_cluster_command(args) -> int:
  """Run cluster configuration command to set the kubectl config.

  Args:
    args: user provided arguments for running the command.

  Returns:
    0 if successful and 1 otherwise.
  """
  command = (
      'gcloud container clusters get-credentials'
      f' {args.cluster} --region={zone_to_region(args.zone)}'
      f' --project={args.project} &&'
      ' kubectl config view && kubectl config set-context --current'
      ' --namespace=default'
  )
  task = f'get-credentials to cluster {args.cluster}'
  return_code = run_command_with_updates_retry(
      command, task, args, verbose=False
  )
  if return_code != 0:
    xpk_print(f'{task} returned ERROR {return_code}')
  return return_code
