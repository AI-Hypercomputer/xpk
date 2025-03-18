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

from tabulate import tabulate

from ..core.capacity import H100_DEVICE_TYPE
from ..core.cluster import (
    get_all_clusters_programmatic,
    get_cluster_credentials,
    install_nccl_on_cluster,
    set_jobset_on_cluster,
    setup_k8s_env,
    update_cluster_with_gcsfuse_driver_if_necessary,
    update_cluster_with_workload_identity_if_necessary,
)
from ..core.cluster_private import authorize_private_cluster_access_if_necessary
from ..core.commands import run_command_for_value, run_command_with_updates
from ..core.config import VERTEX_TENSORBOARD_FEATURE_FLAG
from ..core.gcloud_context import (
    add_zone_and_project,
    get_gke_control_plane_version,
    get_gke_server_config,
    zone_to_region,
)
from ..core.kjob import apply_kjob_crds, prepare_kjob, verify_kjob_installed
from ..core.kueue import (
    cluster_preheat_yml,
    install_kueue_crs,
    install_kueue_on_cluster,
    wait_for_kueue_available,
)
from ..core.nap import enable_autoprovisioning_on_cluster
from ..core.network import (
    create_cluster_network_config,
    delete_cluster_subnets,
    set_up_cluster_network_for_gpu,
)
from ..core.nodepool import get_gke_node_pool_version, run_gke_node_pool_create_command
from ..core.ray import install_ray_cluster
from ..core.resources import create_cluster_configmaps
from ..core.storage import install_storage_crd
from ..core.system_characteristics import (
    AcceleratorType,
    AcceleratorTypeToAcceleratorCharacteristics,
    SystemCharacteristics,
    get_system_characteristics,
)
from ..core.vertex import create_vertex_tensorboard
from ..core.workload import get_workload_list
from ..utils.console import get_user_input, xpk_exit, xpk_print
from ..utils.file import write_tmp_file
from . import cluster_gcluster
from .common import set_cluster_command
from ..core.cluster import update_cluster_with_gcpfilestore_driver_if_necessary


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

  if system.device_type in cluster_gcluster.supported_device_types:
    xpk_print(
        'Creating the cluster using Cluster Toolkit. Machine Type:'
        f' {system.gce_machine_type} ...'
    )
    cluster_gcluster.cluster_create(args)
    xpk_exit(0)

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

  authorize_private_cluster_access_command_code = (
      authorize_private_cluster_access_if_necessary(args)
  )
  if authorize_private_cluster_access_command_code != 0:
    xpk_exit(authorize_private_cluster_access_command_code)

  # ToDo(roshanin@) - Re-enable CloudDNS on Pathways clusters conditionally.
  # Enable WorkloadIdentity if not enabled already.
  if (
      args.enable_workload_identity
      or args.enable_gcsfuse_csi_driver
      or args.enable_gcpfilestore_csi_driver
  ):
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

  if args.enable_gcpfilestore_csi_driver:
    update_cluster_command_code = (
        update_cluster_with_gcpfilestore_driver_if_necessary(args)
    )
    if update_cluster_command_code != 0:
      xpk_exit(update_cluster_command_code)

  # Update Pathways clusters with CloudDNS if not enabled already.

  get_cluster_credentials(args)

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

  if system.device_type == H100_DEVICE_TYPE:
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

  xpk_print('Creating ConfigMap for cluster')
  create_cluster_configmaps_code = create_cluster_configmaps(
      args, system, tensorboard_config, autoprovisioning_config
  )
  if create_cluster_configmaps_code != 0:
    xpk_exit(create_cluster_configmaps_code)

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

  xpk_print('Verifying kjob installation')
  err_code = verify_kjob_installed(args)
  if err_code > 0:
    xpk_exit(err_code)

  xpk_print('Applying kjob CDRs')
  err_code = apply_kjob_crds(args)
  if err_code > 0:
    xpk_exit(err_code)

  err_code = prepare_kjob(args)
  if err_code > 0:
    xpk_exit(err_code)

  k8s_client = setup_k8s_env(args)
  install_storage_crd(k8s_client)

  xpk_print('Wait for Kueue to be fully available')
  wait_for_kueue_available_code = wait_for_kueue_available(args)
  if wait_for_kueue_available_code != 0:
    xpk_exit(wait_for_kueue_available_code)

  xpk_print('Install Kueue Custom Resources')
  enable_kueue_credentials_code = install_kueue_crs(
      args, system, autoprovisioning_config
  )
  if enable_kueue_credentials_code != 0:
    xpk_exit(enable_kueue_credentials_code)

  if system.accelerator_type == AcceleratorType['GPU']:
    xpk_print('Installing NCCL Plugin for cluster')
    install_nccl_code = install_nccl_on_cluster(args, system)
    if install_nccl_code != 0:
      xpk_exit(install_nccl_code)

  if args.enable_ray_cluster:
    return_code = install_ray_cluster(args, system)
    if return_code != 0:
      xpk_print('Installation of RayCluster failed.')
      xpk_exit(return_code)

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

  if cluster_gcluster.created_by_gcluster(args):
    xpk_print(f'Deleting {args.cluster} cluster using Cluster Toolkit...')
    cluster_gcluster.cluster_delete(args)
    xpk_exit(0)

  set_cluster_command_code = set_cluster_command(args)
  if set_cluster_command_code != 0:
    xpk_exit(set_cluster_command_code)

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

  get_cluster_credentials(args)
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

  get_cluster_credentials(args)

  return_code, data_table = nodepools_build_table(args)
  if return_code != 0:
    xpk_exit(return_code)

  if len(data_table) > 1:
    xpk_print(
        'Nodepools info:\n',
        tabulate(data_table, headers='firstrow', tablefmt='plain'),
    )
  else:
    xpk_print('No nodepools info found')

  return_code_node_output, node_output = run_command_for_value(
      r'kubectl get node --no-headers=true'
      r" --selector='cloud.google.com/gke-tpu-accelerator' | wc -l",
      'Count TPU Nodes',
      args,
  )
  if return_code_node_output != 0:
    xpk_exit(return_code_node_output)
  node_output = node_output.splitlines()[-1]
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


def nodepools_build_table(args) -> tuple[int, list[list]]:
  table = [[
      'NODEPOOL_NAME',
      'SLICE',
      'TYPE',
      'EXPECTED_HEALTHY_NODES',
      'ACTUAL_HEALTHY_NODES',
      'TOTAL_NODES',
  ]]

  nodepools_data = {}

  nodepools, return_code = get_node_pools_name(args)
  if return_code != 0:
    xpk_print(f'Get node pools name returned ERROR {return_code}')

  for name in nodepools:
    nodepools_data[name] = [name]

  slices, return_code = get_slice_node_pool_size(args)
  if return_code != 0:
    xpk_print(f'Get slice node pool size returned ERROR {return_code}')

  for line in slices:
    s = line.split()
    count, nodepool_name = s[0], s[1]
    nodepools_data[nodepool_name].append(count)

  type_nodepool, return_code = get_node_pool_instance_type(args)
  if return_code != 0:
    xpk_print(f'Get node pool instance type returned ERROR {return_code}')

  for line in type_nodepool:
    tn = line.split()
    nodepool_name, instance_type = tn[0], tn[1]
    nodepools_data[nodepool_name].append(instance_type)

  expected_healthy_nodes, return_code = get_expected_healthy_nodes(args)
  if return_code != 0:
    xpk_print(f'Get expected healthy nodes returned ERROR {return_code}')

  for line in expected_healthy_nodes:
    ehn = line.split()
    count, nodepool_name = ehn[0], ehn[1]
    nodepools_data[nodepool_name].append(count)

  actual_healthy_nodes, return_code = get_actual_healthy_nodes(args)
  if return_code != 0:
    xpk_print(f'Get actual healthy nodes returned ERROR {return_code}')

  for line in actual_healthy_nodes:
    ahn = line.split()
    count, nodepool_name = ahn[0], ahn[1]
    nodepools_data[nodepool_name].append(count)

  total_nodes, return_code = get_total_nodes_per_node_pool(args)
  if return_code != 0:
    xpk_print(f'Get total nodes per node pool returned ERROR {return_code}')

  for line in total_nodes:
    tn = line.split()
    count, nodepool_name = tn[0], tn[1]
    nodepools_data[nodepool_name].append(count)

  for _, np_data in nodepools_data.items():
    table.append(np_data)

  return 0, table


def get_node_pools_name(args) -> tuple[list[str], int]:
  cmd_nodepools = (
      'kubectl get node --no-headers=true -o'
      " custom-columns='NODEPOOL:.metadata.labels.cloud\\.google\\.com/gke-nodepool'"
      " | grep -v 'none' | sort | uniq"
  )
  return_code, out = run_command_for_value(cmd_nodepools, 'Nodepool list', args)
  if return_code != 0:
    return [], return_code

  return out.splitlines(), 0


def get_slice_node_pool_size(args) -> tuple[list[str], int]:
  cmd_slices = (
      'kubectl get node --no-headers=true -o'
      " custom-columns=':metadata.labels.cloud\\.google\\.com/gke-nodepool'"
      " | grep -v 'none'"
      ' | sort'
      ' | uniq -c'
  )
  return_code, out = run_command_for_value(
      cmd_slices, 'Count nodes per nodepool slice', args
  )
  if return_code != 0:
    return [], return_code

  return out.splitlines(), 0


def get_node_pool_instance_type(args) -> tuple[list[str], int]:
  cmd_type_nodepool = (
      'kubectl get node --no-headers=true -o'
      " custom-columns='NODEPOOL:.metadata.labels.cloud\\.google\\.com/gke-nodepool,"
      " TYPE:.metadata.labels.node\\.kubernetes\\.io/instance-type' | grep -v"
      " 'none' | sort | uniq"
  )
  return_code, out = run_command_for_value(
      cmd_type_nodepool, 'Instance type of nodepools', args
  )
  if return_code != 0:
    return [], return_code

  return out.splitlines(), 0


def get_expected_healthy_nodes(args) -> tuple[list[str], int]:
  cmd_expected_healthy_nodes = (
      'kubectl get node --no-headers=true -o'
      " custom-columns=':metadata.labels.cloud\\.google\\.com/gke-nodepool'"
      " | grep -v 'none'"
      ' | sort'
      ' | uniq -c'
  )
  return_code, out = run_command_for_value(
      cmd_expected_healthy_nodes,
      'Count expected healthy nodes per nodepool',
      args,
  )
  if return_code != 0:
    return [], return_code

  return out.splitlines(), 0


def get_actual_healthy_nodes(args) -> tuple[list[str], int]:
  cmd_actual_healthy_nodes = (
      'kubectl get node --no-headers=true -o'
      " custom-columns='NODE_NAME:metadata.name,"
      ' READY_STATUS:.status.conditions[?(@.type=="Ready")].status,'
      " NODEPOOL:metadata.labels.cloud\\.google\\.com/gke-nodepool' "
      ' | grep -w True'
      " | grep -v 'none'"
      " | awk {'print $3'}"
      ' | sort'
      ' | uniq -c'
  )
  return_code, out = run_command_for_value(
      cmd_actual_healthy_nodes, 'Count actual healthy nodes per nodepool', args
  )
  if return_code != 0:
    return [], return_code

  return out.splitlines(), 0


def get_total_nodes_per_node_pool(args) -> tuple[list[str], int]:
  cmd_total_nodes = (
      'kubectl get node --no-headers=true -o'
      " custom-columns='NODE_NAME:metadata.name,"
      ' READY_STATUS:.status.conditions[?(@.type=="Ready")].status,'
      " NODEPOOL:metadata.labels.cloud\\.google\\.com/gke-nodepool'"
      " | grep -v 'none'"
      " | awk {'print $3'}"
      ' | sort'
      ' | uniq -c'
  )
  return_code, out = run_command_for_value(
      cmd_total_nodes, 'Count total nodes per nodepool', args
  )
  if return_code != 0:
    return [], return_code

  return out.splitlines(), 0


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
  args.enable_ray_cluster = False
  cluster_create(args)


def cluster_create_ray_cluster(args) -> None:
  """Function around cluster creation for RayCluster.

  Args:
    args: user provided arguments for running the command.

  Returns:
    None
  """
  args.enable_ray_cluster = True
  args.enable_autoprovisioning = False
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
  if not args.force:
    xpk_print('Get the name of the workloads in the cluster.')
    args.filter_by_status = 'EVERYTHING'
    return_code, return_value = get_workload_list(args)
    if return_code != 0:
      xpk_print(f'List Job request returned ERROR {return_code}')
      return return_code

    # Ignore Column Names line.
    if len(return_value) > 1:
      workloads = [x.split(' ')[0] for x in return_value.splitlines()][1:]
      if workloads and not get_user_input(
          f'Planning to delete {len(workloads)} workloads in the cluster'
          f' {args.cluster} including {workloads}. \nDo you wish to delete: y'
          ' (yes) / n (no):\n'
      ):
        xpk_print('Skipping delete command.')
        return 0

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

  # If the user passes in the gke version then we use that directly instead of the rapid release.
  # This allows users to directly pass a specified gke version without release channel constraints.
  rapid_release_cmd = ''
  if args.gke_version is not None:
    rapid_release_cmd = ' --release-channel rapid'

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
      f' {rapid_release_cmd}'
  )

  enable_ip_alias = False

  if args.private or args.authorized_networks is not None:
    enable_ip_alias = True
    command += ' --enable-master-authorized-networks --enable-private-nodes'

  if system.accelerator_type == AcceleratorType['GPU']:
    enable_ip_alias = True
    command += (
        ' --enable-dataplane-v2'
        ' --enable-multi-networking --no-enable-autoupgrade'
    )
  else:
    command += ' --location-policy=BALANCED --scopes=storage-full,gke-default'

    if args.enable_pathways:
      enable_ip_alias = True

  if enable_ip_alias:
    command += ' --enable-ip-alias'

  if args.enable_ray_cluster:
    command += ' --addons RayOperator'

  if (
      args.enable_workload_identity
      or args.enable_gcsfuse_csi_driver
      or args.enable_gcpfilestore_csi_driver
  ):
    command += f' --workload-pool={args.project}.svc.id.goog'

  addons = []
  if args.enable_gcsfuse_csi_driver:
    addons.append('GcsFuseCsiDriver')

  if args.enable_gcpfilestore_csi_driver:
    addons.append('GcpFilestoreCsiDriver')

  if len(addons) > 0:
    addons_str = ','.join(addons)
    command += f' --addons={addons_str}'

  return_code = run_command_with_updates(command, 'GKE Cluster Create', args)
  if return_code != 0:
    xpk_print(f'GKE Cluster Create request returned ERROR {return_code}')
    return 1
  return 0
