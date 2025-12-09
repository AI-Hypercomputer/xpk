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

from ..utils.feature_flags import FeatureFlags
from ..utils.versions import ReleaseChannel
from ..core.pathways import get_pathways_machine_types
from ..core.capacity import H100_DEVICE_TYPE, get_reservation_deployment_type, parse_reservation
from ..core.cluster import (
    get_all_clusters_programmatic,
    get_cluster_credentials,
    install_nccl_on_cluster,
    install_nri_on_cluster,
    set_jobset_on_cluster,
    set_pathways_job_on_cluster,
    setup_k8s_env,
    count_nodes_on_cluster,
    update_cluster_with_gcpfilestore_driver_if_necessary,
    update_cluster_with_gcsfuse_driver_if_necessary,
    update_cluster_with_parallelstore_driver_if_necessary,
    update_cluster_with_pd_driver_if_necessary,
    update_cluster_with_lustre_driver_if_necessary,
    update_cluster_with_workload_identity_if_necessary,
)
from ..core.cluster_private import authorize_private_cluster_access_if_necessary
from ..core.commands import run_command_for_value, run_command_with_updates
from ..core.config import VERTEX_TENSORBOARD_FEATURE_FLAG
from ..core.telemetry import MetricsCollector, MetricsEventMetadataKey
from ..core.capacity import get_capacity_type
from ..core.gcloud_context import (
    add_zone_and_project,
    get_gke_control_plane_version,
    get_gke_server_config,
    get_cluster_location,
    zone_to_region,
)
from ..core.jobset import update_jobset_resources_if_necessary
from ..core.kueue_manager import (KueueConfig, KueueManager)
from ..core.nap import enable_autoprovisioning_on_cluster
from ..core.network import (
    create_cluster_network_config,
    delete_cluster_subnets,
    set_up_cluster_network_for_a3,
)
from ..core.nodepool import (
    get_gke_node_pool_version,
    run_gke_node_pool_create_command,
)
from ..core.ray import install_ray_cluster
from ..core.mtc import install_mtc_on_cluster
from ..core.resources import AutoprovisioningConfig, create_cluster_configmaps
from ..core.scheduling import get_total_chips_requested_from_args
from ..core.storage import install_storage_crd
from ..core.system_characteristics import (
    AcceleratorType,
    AcceleratorTypeToAcceleratorCharacteristics,
    SystemCharacteristics,
    get_system_characteristics,
)
from ..core.vertex import create_vertex_tensorboard
from ..core.workload import get_workload_list
from ..utils.console import ask_for_user_consent, xpk_exit, xpk_print
from ..utils.file import write_tmp_file
from ..utils.execution_context import is_dry_run, is_quiet
from ..utils.validation import validate_dependencies_list, SystemDependency, should_validate_dependencies
from . import cluster_gcluster
from .common import set_cluster_command, validate_sub_slicing_system, validate_super_slicing_system
from jinja2 import Environment, FileSystemLoader
from ..utils.templates import get_templates_absolute_path
import shutil
import os
from .managed_ml_diagnostics import install_mldiagnostics_prerequisites

CLUSTER_PREHEAT_JINJA_FILE = 'cluster_preheat.yaml.j2'


def cluster_adapt(args) -> None:
  """Function that performs cluster adaptation.

  Args:
    args: user provided arguments for running the command.
  """
  if should_validate_dependencies(args):
    validate_dependencies_list([
        SystemDependency.KUBECTL,
        SystemDependency.GCLOUD,
    ])
  args.enable_pathways = False

  system, return_code = get_system_characteristics(args)

  if return_code > 0 or system is None:
    xpk_print('Fetching system characteristics failed!')
    xpk_exit(return_code)

  xpk_print(
      f'Starting cluster adaptation for cluster {args.cluster}:', flush=True
  )
  add_zone_and_project(args)

  if system.accelerator_type == AcceleratorType.GPU and not getattr(
      args, 'num_nodes'
  ):
    xpk_print(
        'Argument --num-nodes was not provided, trying to determine number of'
        ' nodes based on the available nodes in the cluster...'
    )
    args.num_nodes = count_nodes_on_cluster(system)
    if args.num_nodes == 0:
      xpk_print(
          'Found unexpected number of nodes. Is the --device-type correct?'
      )
      xpk_exit(1)
    else:
      xpk_print(f'Using {args.num_nodes} nodes.')

  # ToDo(roshanin@) - Re-enable CloudDNS on Pathways clusters conditionally.
  # Enable WorkloadIdentity if not enabled already.
  if args.enable_workload_identity or args.enable_gcsfuse_csi_driver:
    update_cluster_command_code = (
        update_cluster_with_workload_identity_if_necessary(args)
    )
    if update_cluster_command_code != 0:
      xpk_exit(update_cluster_command_code)

  get_cluster_credentials(args)

  if not is_dry_run():
    k8s_client = setup_k8s_env(args)
    install_storage_crd(k8s_client)

  install_storage_csis(args)

  # create Vertex Tensorboard for new and existing clusters if create-vertex-tensorboard is set
  tensorboard_config = {}
  if VERTEX_TENSORBOARD_FEATURE_FLAG and args.create_vertex_tensorboard:
    tensorboard_config = create_vertex_tensorboard(args)
    # exit if failed to create Tensorboard in Vertex AI
    if not tensorboard_config:
      xpk_exit(1)

  autoprovisioning_config = None
  if args.enable_autoprovisioning:
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

  # TODO: Uncomment when cluster_adapt will support TPU cluters
  # set_pathways_job_on_cluster_code = set_pathways_job_on_cluster(args)
  # if set_pathways_job_on_cluster_code != 0:
  #   xpk_exit(set_pathways_job_on_cluster_code)

  install_kueue_code = _install_kueue(args, system, autoprovisioning_config)
  if install_kueue_code != 0:
    xpk_exit(install_kueue_code)

  if system.accelerator_type == AcceleratorType.GPU:
    prepare_gpus(system)

  if args.enable_ray_cluster:
    return_code = install_ray_cluster(args, system)
    if return_code != 0:
      xpk_print('Installation of RayCluster failed.')
      xpk_exit(return_code)

  xpk_print('GKE commands done! Resources are created.')
  xpk_print(
      'See your GKE Cluster here:'
      # pylint: disable=line-too-long
      f' https://console.cloud.google.com/kubernetes/clusters/details/{get_cluster_location(args.project, args.cluster, args.zone)}/{args.cluster}/details?project={args.project}'
  )
  xpk_exit(0)


def _validate_cluster_create_args(args, system: SystemCharacteristics):
  if FeatureFlags.SUB_SLICING_ENABLED and args.sub_slicing:
    validate_sub_slicing_system(system)
    _validate_sub_slicing_reservation(args)
  if FeatureFlags.SUPER_SLICING_ENABLED:
    _validate_num_slices_and_set_default(args)
    if args.super_slicing:
      validate_super_slicing_system(system)
      _validate_super_slicing_reservation(args)
  if args.enable_pathways:
    _validate_pathways_machine(args)


def _validate_pathways_machine(args):
  return_code, result = get_pathways_machine_types(
      project=args.project, zone=args.zone
  )
  if return_code != 0:
    xpk_print('Error: Unable to retrieve available pathways machine types')
    xpk_exit(1)

  if args.pathways_gce_machine_type not in result:
    xpk_print(
        'Error: Invalid --pathways-gce-machine-type. Specify machine type that'
        ' has at least 100GB of memory and at least 49 CPUs.'
    )
    xpk_print(f'Available machine types: {", ".join(result)}')
    xpk_exit(1)


def _validate_sub_slicing_reservation(args):
  _validate_gsc_reservation(args, 'Sub-slicing')


def _validate_super_slicing_reservation(args):
  _validate_gsc_reservation(args, 'Super-slicing')
  reservation = parse_reservation(args.reservation, args.project)
  if reservation.block_name is None:
    xpk_print(
        'Error: Validation failed: Super-slicing cluster creation'
        ' requires a block or sub-block reservation.'
    )
    xpk_exit(1)


def _validate_gsc_reservation(args, creation_description: str):
  if args.reservation is None:
    xpk_print(
        f'Error: Validation failed: {creation_description} cluster creation'
        ' requires Cluster Director reservation to be specified.'
    )
    xpk_exit(1)

  deployment_type = get_reservation_deployment_type(
      reservation_path=args.reservation, project=args.project, zone=args.zone
  )
  if deployment_type != 'DENSE':
    xpk_print(
        'Error: Validation failed: The specified reservation'
        f' "{args.reservation}" is not a Cluster Director reservation.'
    )
    xpk_print(
        'Please provide a reservation created for Cluster Director to proceed.'
    )
    xpk_print('To list valid Cluster Director reservations, run:')
    xpk_print(
        '  gcloud compute reservations list --filter="deploymentType=DENSE"'
    )
    xpk_print(
        'Refer to the documentation for more information on creating Cluster'
        ' Director reservations:'
        ' https://cloud.google.com/cluster-director/docs/reserve-capacity'
    )
    xpk_exit(1)


def _validate_num_slices_and_set_default(args):
  if args.num_cubes is not None and not args.super_slicing:
    xpk_print('--num-cubes can only be used with --super-slicing')
    xpk_exit(1)

  if (
      args.num_cubes is not None
      and args.num_slices is not None
      and args.num_cubes != args.num_slices
  ):
    xpk_print('--num-cubes must not be different from --num-slices')
    xpk_exit(1)

  args.num_slices = args.num_slices or args.num_cubes or 1


def cluster_create(args) -> None:
  """Function around cluster creation.

  Args:
    args: user provided arguments for running the command.
  """
  if should_validate_dependencies(args):
    validate_dependencies_list([
        SystemDependency.KUBECTL,
        SystemDependency.GCLOUD,
    ])

  system, return_code = get_system_characteristics(args)
  if return_code > 0 or system is None:
    xpk_print('Fetching system characteristics failed!')
    xpk_exit(return_code)

  xpk_print(f'Starting cluster create for cluster {args.cluster}:', flush=True)
  add_zone_and_project(args)

  _validate_cluster_create_args(args, system)
  _log_cluster_create_telemetry(args)

  release_channel = (
      ReleaseChannel.REGULAR if args.gke_version else ReleaseChannel.RAPID
  )

  return_code, gke_server_config = get_gke_server_config(
      args, release_channel=release_channel
  )
  if return_code != 0 or gke_server_config is None:
    xpk_exit(return_code)

  return_code, gke_control_plane_version = get_gke_control_plane_version(
      args, gke_server_config
  )
  if return_code != 0 or gke_control_plane_version is None:
    xpk_exit(return_code)

  if system.device_type in cluster_gcluster.supported_device_types:
    xpk_print(
        'Creating the cluster using Cluster Toolkit. Machine Type:'
        f' {system.gce_machine_type} ...'
    )
    cluster_gcluster.cluster_create(
        args,
        gke_control_plane_version=gke_control_plane_version,
        release_channel=release_channel,
    )
    xpk_exit(0)

  create_cluster_command_code = create_cluster_if_necessary(
      args, gke_control_plane_version, system, release_channel=release_channel
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
  if args.enable_workload_identity or args.enable_gcsfuse_csi_driver:
    update_cluster_command_code = (
        update_cluster_with_workload_identity_if_necessary(args)
    )
    if update_cluster_command_code != 0:
      xpk_exit(update_cluster_command_code)

  get_cluster_credentials(args)

  update_coredns_command_code = update_coredns_if_necessary()
  if update_coredns_command_code != 0:
    xpk_exit(update_cluster_command_code)

  if not is_dry_run():
    k8s_client = setup_k8s_env(args)
    install_storage_crd(k8s_client)

  install_storage_csis(args)

  # create Vertex Tensorboard for new and existing clusters if create-vertex-tensorboard is set
  tensorboard_config = {}
  if VERTEX_TENSORBOARD_FEATURE_FLAG and args.create_vertex_tensorboard:
    tensorboard_config = create_vertex_tensorboard(args)
    # exit if failed to create Tensorboard in Vertex AI
    if not tensorboard_config:
      xpk_exit(1)

  if system.device_type == H100_DEVICE_TYPE:
    xpk_print('Setting up Network for cluster')
    set_up_cluster_network_code = set_up_cluster_network_for_a3(args)
    if set_up_cluster_network_code != 0:
      xpk_exit(set_up_cluster_network_code)

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
  assert gke_node_pool_version

  run_gke_node_pool_create_command_code = run_gke_node_pool_create_command(
      args, system, gke_node_pool_version
  )
  if run_gke_node_pool_create_command_code != 0:
    xpk_exit(run_gke_node_pool_create_command_code)

  # Provision node pools dynamically based on incoming workloads:
  # Currently autoprovisioning is not supported with Pathways.
  autoprovisioning_config = None
  if args.enable_autoprovisioning:
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
  update_jobset_resources_code = update_jobset_resources_if_necessary()
  if update_jobset_resources_code != 0:
    xpk_exit(update_jobset_resources_code)

  set_pathways_job_on_cluster_code = set_pathways_job_on_cluster(args)
  if set_pathways_job_on_cluster_code != 0:
    xpk_exit(set_pathways_job_on_cluster_code)

  install_kueue_code = _install_kueue(args, system, autoprovisioning_config)
  if install_kueue_code != 0:
    xpk_exit(install_kueue_code)

  if system.accelerator_type == AcceleratorType.GPU:
    prepare_gpus(system)

  if args.enable_ray_cluster:
    return_code = install_ray_cluster(args, system)
    if return_code != 0:
      xpk_print('Installation of RayCluster failed.')
      xpk_exit(return_code)

  if hasattr(args, 'enable_mtc') and args.enable_mtc:
    return_code = install_mtc_on_cluster(args, system)
    if return_code != 0:
      xpk_print('Installation of MTC failed.')
      xpk_exit(return_code)

  xpk_print('GKE commands done! Resources are created.')
  xpk_print(
      'See your GKE Cluster here:'
      # pylint: disable=line-too-long
      f' https://console.cloud.google.com/kubernetes/clusters/details/{get_cluster_location(args.project, args.cluster, args.zone)}/{args.cluster}/details?project={args.project}'
  )

  if args.managed_mldiagnostics:
    return_code = install_mldiagnostics_prerequisites()
    if return_code != 0:
      xpk_print('Installation of MLDiagnostics failed.')
      xpk_exit(return_code)

  xpk_exit(0)


def cluster_delete(args) -> None:
  """Function around cluster delete.

  Args:
    args: user provided arguments for running the command.

  Returns:
    0 if successful and 1 otherwise.
  """
  if should_validate_dependencies(args):
    validate_dependencies_list([SystemDependency.GCLOUD])
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
  if should_validate_dependencies(args):
    validate_dependencies_list(
        [SystemDependency.KUBECTL, SystemDependency.GCLOUD]
    )
  xpk_print(
      f'Starting cluster cacheimage for cluster: {args.cluster}', flush=True
  )
  add_zone_and_project(args)

  get_cluster_credentials(args)
  system, return_code = get_system_characteristics(args)

  if return_code > 0 or system is None:
    xpk_print('Fetching system characteristics failed!')
    xpk_exit(return_code)

  node_selector_key = AcceleratorTypeToAcceleratorCharacteristics[
      system.accelerator_type
  ].accelerator_label

  template_env = Environment(
      loader=FileSystemLoader(searchpath=get_templates_absolute_path())
  )
  cluster_preheat_yaml = template_env.get_template(CLUSTER_PREHEAT_JINJA_FILE)
  rendered_yaml = cluster_preheat_yaml.render(
      cachekey=args.cache_key,
      image_name=args.docker_image,
      nodeSelectorKey=node_selector_key,
  )
  tmp = write_tmp_file(rendered_yaml)
  command_apply = f'kubectl apply -f {str(tmp)}'
  command_delete = f'kubectl delete -f {str(tmp)} --ignore-not-found=true'

  return_code = run_command_with_updates(
      command_delete, 'Deleting Cached Image'
  )
  if return_code != 0:
    xpk_print(f'Delete Cached Image returned ERROR {return_code}')
    xpk_exit(return_code)

  return_code = run_command_with_updates(command_apply, 'Creating Cached Image')
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
  if should_validate_dependencies(args):
    validate_dependencies_list(
        [SystemDependency.KUBECTL, SystemDependency.GCLOUD]
    )
  xpk_print(f'Starting nodepool list for cluster: {args.cluster}', flush=True)
  add_zone_and_project(args)

  get_cluster_credentials(args)

  return_code, data_table = nodepools_build_table()
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
  )
  if return_code_node_output != 0:
    xpk_exit(return_code_node_output)
  node_output = node_output.splitlines()[-1]
  number_tpu_vms_in_cluster = int(node_output)

  return_code_pod_output, pod_output = run_command_for_value(
      "kubectl get pod -o=custom-columns='Status:.status.phase' | grep -i"
      ' Running | wc -l',
      'Count TPU Pods',
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


def nodepools_build_table() -> tuple[int, list[list]]:
  table = [[
      'NODEPOOL_NAME',
      'SLICE',
      'TYPE',
      'EXPECTED_HEALTHY_NODES',
      'ACTUAL_HEALTHY_NODES',
      'TOTAL_NODES',
  ]]

  nodepools_data = {}

  nodepools, return_code = get_node_pools_name()
  if return_code != 0:
    xpk_print(f'Get node pools name returned ERROR {return_code}')

  for name in nodepools:
    nodepools_data[name] = [name]

  slices, return_code = get_slice_node_pool_size()
  if return_code != 0:
    xpk_print(f'Get slice node pool size returned ERROR {return_code}')

  for line in slices:
    s = line.split()
    count, nodepool_name = s[0], s[1]
    nodepools_data[nodepool_name].append(count)

  type_nodepool, return_code = get_node_pool_instance_type()
  if return_code != 0:
    xpk_print(f'Get node pool instance type returned ERROR {return_code}')

  for line in type_nodepool:
    tn = line.split()
    nodepool_name, instance_type = tn[0], tn[1]
    nodepools_data[nodepool_name].append(instance_type)

  expected_healthy_nodes, return_code = get_expected_healthy_nodes()
  if return_code != 0:
    xpk_print(f'Get expected healthy nodes returned ERROR {return_code}')

  for line in expected_healthy_nodes:
    ehn = line.split()
    count, nodepool_name = ehn[0], ehn[1]
    nodepools_data[nodepool_name].append(count)

  actual_healthy_nodes, return_code = get_actual_healthy_nodes()
  if return_code != 0:
    xpk_print(f'Get actual healthy nodes returned ERROR {return_code}')

  for line in actual_healthy_nodes:
    ahn = line.split()
    count, nodepool_name = ahn[0], ahn[1]
    nodepools_data[nodepool_name].append(count)

  total_nodes, return_code = get_total_nodes_per_node_pool()
  if return_code != 0:
    xpk_print(f'Get total nodes per node pool returned ERROR {return_code}')

  for line in total_nodes:
    tn = line.split()
    count, nodepool_name = tn[0], tn[1]
    nodepools_data[nodepool_name].append(count)

  for _, np_data in nodepools_data.items():
    table.append(np_data)

  return 0, table


def get_node_pools_name() -> tuple[list[str], int]:
  cmd_nodepools = (
      'kubectl get node --no-headers=true -o'
      " custom-columns='NODEPOOL:.metadata.labels.cloud\\.google\\.com/gke-nodepool'"
      " | grep -v 'none' | sort | uniq"
  )
  return_code, out = run_command_for_value(cmd_nodepools, 'Nodepool list')
  if return_code != 0:
    return [], return_code

  return out.splitlines(), 0


def get_slice_node_pool_size() -> tuple[list[str], int]:
  cmd_slices = (
      'kubectl get node --no-headers=true -o'
      " custom-columns=':metadata.labels.cloud\\.google\\.com/gke-nodepool'"
      " | grep -v 'none'"
      ' | sort'
      ' | uniq -c'
  )
  return_code, out = run_command_for_value(
      cmd_slices, 'Count nodes per nodepool slice'
  )
  if return_code != 0:
    return [], return_code

  return out.splitlines(), 0


def get_node_pool_instance_type() -> tuple[list[str], int]:
  cmd_type_nodepool = (
      'kubectl get node --no-headers=true -o'
      " custom-columns='NODEPOOL:.metadata.labels.cloud\\.google\\.com/gke-nodepool,"
      " TYPE:.metadata.labels.node\\.kubernetes\\.io/instance-type' | grep -v"
      " 'none' | sort | uniq"
  )
  return_code, out = run_command_for_value(
      cmd_type_nodepool, 'Instance type of nodepools'
  )
  if return_code != 0:
    return [], return_code

  return out.splitlines(), 0


def get_expected_healthy_nodes() -> tuple[list[str], int]:
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
  )
  if return_code != 0:
    return [], return_code

  return out.splitlines(), 0


def get_actual_healthy_nodes() -> tuple[list[str], int]:
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
      cmd_actual_healthy_nodes, 'Count actual healthy nodes per nodepool'
  )
  if return_code != 0:
    return [], return_code

  return out.splitlines(), 0


def get_total_nodes_per_node_pool() -> tuple[list[str], int]:
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
      cmd_total_nodes, 'Count total nodes per nodepool'
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
  if should_validate_dependencies(args):
    validate_dependencies_list([SystemDependency.GCLOUD])
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


def install_jq():
  """Installs 'jq' utility."""
  if shutil.which('jq'):
    xpk_print("Task: 'Install jq' skipped, jq already installed.")
    return
  command_jq_install = 'sudo apt install jq -y'
  xpk_print("Task: 'Install jq' in progress.")
  return_code = run_command_with_updates(command_jq_install, 'Install jq')
  if return_code != 0:
    xpk_print(f'Install jq error {return_code}')
    xpk_exit(return_code)


def clone_coredns_deployment_repo(coredns_repo_full_path: str):
  """Clones the CoreDNS deployment repository if it doesn't exist."""
  if os.path.exists(coredns_repo_full_path):
    xpk_print(
        f"Directory '{coredns_repo_full_path}' already exists, skip git clone."
    )
    return
  command_git_clone = (
      'git clone https://github.com/coredns/deployment.git'
      f' {coredns_repo_full_path}'
  )
  xpk_print(
      "Task: 'Clone deployment' in progress, Target"
      f' directory:{coredns_repo_full_path}.'
  )
  return_code = run_command_with_updates(command_git_clone, 'Clone deployment')
  if return_code != 0:
    xpk_print(f'Clone deployment error {return_code}')
    xpk_exit(return_code)


def deploy_coredns_manifests(coredns_k8s_path: str):
  """Deploys CoreDNS manifests to the cluster."""
  if not os.path.isdir(coredns_k8s_path):
    xpk_print(
        f"Error：CoreDNS Kubernetes path '{coredns_k8s_path}' does not exist."
        ' Has git clone been successful?'
    )
    xpk_exit(1)
  original_cwd = os.getcwd()
  try:
    os.chdir(coredns_k8s_path)
    xpk_print(f'Current working directory changed to: {os.getcwd()}')

    command_deploy_coredns = './deploy.sh | kubectl apply -f -'
    xpk_print(
        f"Task: 'Deploy CoreDNS' in progress, Located at '{coredns_k8s_path}'"
    )
    return_code = run_command_with_updates(
        command_deploy_coredns, 'Deploy CoreDNS'
    )
    if return_code != 0:
      xpk_print(f'Deploy CoreDNS error {return_code}')

  finally:
    xpk_print(f'Restoring working directory to: {original_cwd}')
    os.chdir(original_cwd)
  if return_code != 0:
    xpk_exit(return_code)


def scale_down_deployment(deployment_name: str, namespace: str = 'kube-system'):
  """Scales down a specified Kubernetes deployment to 0 replicas."""
  command = (
      f'kubectl scale deployment {deployment_name} --replicas=0'
      f' --namespace={namespace}'
  )
  xpk_print(f"Task: 'Scaling down {deployment_name}' in progress")
  return_code = run_command_with_updates(
      command, f'Scale down {deployment_name}'
  )
  if return_code != 0:
    xpk_print(f'Scale down {deployment_name} error {return_code}')
    xpk_exit(return_code)
  xpk_print(f'{deployment_name} has been scaled down.')


def scale_up_coredns(replicas: int = 15, namespace: str = 'kube-system'):
  """Scales up the CoreDNS deployment to a specified number of replicas."""
  command_coredns_scale = (
      f'kubectl scale deployment coredns --replicas={replicas} -n {namespace}'
  )
  xpk_print(f"Task: 'Scale CoreDNS' in progress (to {replicas} replicas)")
  return_code = run_command_with_updates(command_coredns_scale, 'Scale CoreDNS')
  if return_code != 0:
    xpk_print(f'Scale CoreDNS error {return_code}')
    xpk_exit(return_code)


def check_deployment_exists(deployment_name: str, namespace: str) -> bool:
  """Check for the existence of a specific Deployment in a given namespace."""
  # TODO: rewrite this to be more obvious, check if it is correct
  command = (
      f'kubectl get deployment {deployment_name} -n'
      f' {namespace} --ignore-not-found'
  )
  result = run_command_with_updates(
      command, 'Waiting for kubeDNS to be checked.'
  )
  return result != 0


def verify_coredns_readiness(
    timeout: int = 240, namespace: str = 'kube-system'
):
  """Verifies CoreDNS readiness using kubectl wait commands."""
  xpk_print('Now verifying CoreDNS readiness...')
  kube_dns_exists = check_deployment_exists('kube-dns', namespace)
  if kube_dns_exists:
    # Wait for kube-dns to be fully scaled down
    command_kube_dns_wait_scaled_down = (
        'kubectl wait deployment/kube-dns'
        " --for=jsonpath='{.status.replicas}'=0"
        f' --namespace={namespace} --timeout={timeout}s'
    )
    xpk_print('Verifying if kube-dns has scaled down...')
    return_code_kube_dns = run_command_with_updates(
        command_kube_dns_wait_scaled_down, 'Wait for kube-dns scale down'
    )
    if return_code_kube_dns != 0:
      xpk_print('kube-dns did not scale down successfully within the timeout.')
      xpk_exit(1)  # Exit if kube-dns cannot scale down
    else:
      xpk_print('kube-dns has successfully scaled down.')
  else:
    xpk_print('kube-dns deployment not found.')
  # Wait for CoreDNS to be fully scaled up and available
  command_coredns_wait_available = (
      'kubectl wait deployment/coredns --for=condition=Available=true'
      f' --namespace={namespace} --timeout={timeout}s'
  )
  xpk_print('Verifying if CoreDNS is available...')
  return_code_coredns = run_command_with_updates(
      command_coredns_wait_available, 'Wait for coredns available'
  )
  if return_code_coredns != 0:
    xpk_print(
        'CoreDNS verification failed, it might not have fully started within'
        ' the timeout.'
    )
    xpk_exit(1)  # Exit if coredns cannot become available

  xpk_print('CoreDNS has successfully started and passed verification.')


def cleanup_coredns_repo(coredns_repo_full_path: str):
  """Deletes the cloned CoreDNS deployment directory."""
  xpk_print(
      "Task: 'Deleting CoreDNS deployment directory' in progress:"
      f' {coredns_repo_full_path}'
  )
  try:
    shutil.rmtree(coredns_repo_full_path)
    xpk_print(f'Successfully deleted directory: {coredns_repo_full_path}')
  except OSError as e:
    xpk_print(f'Error deleting directory {coredns_repo_full_path}: {e}')


def update_coredns() -> int:
  """Updates and deploys CoreDNS within a cluster.

  Returns:
    0 if successful and 1 otherwise.
  """
  coredns_repo_dir = os.path.expanduser('/tmp/')
  coredns_repo_dir_name = 'deployment'
  coredns_repo_full_path = os.path.join(coredns_repo_dir, coredns_repo_dir_name)
  coredns_k8s_path = os.path.join(coredns_repo_full_path, 'kubernetes')
  # 1. Install jq
  install_jq()

  # 2. Clone CoreDNS deployment repository
  clone_coredns_deployment_repo(coredns_repo_full_path)

  # 3. Deploy CoreDNS to the cluster
  deploy_coredns_manifests(coredns_k8s_path)

  # 4. Scale down kube-dns-autoscaler
  scale_down_deployment('kube-dns-autoscaler')

  # 5. Scale down kube-dns
  scale_down_deployment('kube-dns')

  # 6. Scale up coredns and verify readiness
  scale_up_coredns(replicas=15)
  verify_coredns_readiness()

  xpk_print('The CoreDNS setup process has been completed.')

  # 7. Cleanup
  cleanup_coredns_repo(coredns_repo_full_path)

  return 0


def coredns_deployment_exists(namespace: str = 'kube-system') -> bool:
  """Checks if the CoreDNS deployment exists in the given namespace.

  Args:
    namespace: The Kubernetes namespace to check for the CoreDNS deployment.

  Returns:
    True if the 'coredns' deployment exists, False otherwise.
  """
  command = f'kubectl get deployment coredns -n {namespace}'
  xpk_print(
      "Task: 'Checking CoreDNS deployment existence' in progress for"
      f' namespace: {namespace}'
  )
  return_code = run_command_with_updates(
      command, f'Check CoreDNS deployment in {namespace}'
  )
  if return_code == 0:
    verify_coredns_readiness()
    xpk_print(f"CoreDNS deployment 'coredns' found in namespace '{namespace}'.")
    return True
  else:
    xpk_print(
        f"CoreDNS deployment 'coredns' NOT found in namespace '{namespace}' or"
        ' an error occurred.'
    )
    return False


def update_coredns_if_necessary() -> int:
  """Updates and deploys CoreDNS within the cluster if it's not already present.

  This function checks for the existence of the CoreDNS deployment.
  If it's not found, it proceeds to deploy and configure CoreDNS.

  Returns:
    0 if successful (CoreDNS was already present or successfully deployed),
    and 1 otherwise.
  """
  if coredns_deployment_exists(namespace='kube-system'):
    xpk_print('Skipping CoreDNS deployment since it already exists.')
    return 0
  else:
    xpk_print('CoreDNS deployment not found. Proceeding with CoreDNS setup.')
    return update_coredns()


def create_cluster_if_necessary(
    args,
    gke_control_plane_version: str,
    system: SystemCharacteristics,
    release_channel: ReleaseChannel,
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
        args, gke_control_plane_version, system, release_channel=release_channel
    )


def run_gke_cluster_delete_command(args) -> int:
  """Run the Delete GKE Cluster request.

  Args:
    args: user provided arguments for running the command.

  Returns:
    0 if successful and 1 otherwise.
  """
  if not is_quiet():
    xpk_print('Get the name of the workloads in the cluster.')
    args.filter_by_status = 'EVERYTHING'
    return_code, return_value = get_workload_list(args)
    if return_code != 0:
      xpk_print(f'List Job request returned ERROR {return_code}')
      return return_code

    # Ignore Column Names line.
    if len(return_value) > 1:
      workloads = [x.split(' ')[0] for x in return_value.splitlines()][1:]
      if workloads and not ask_for_user_consent(
          f'Planning to delete {len(workloads)} workloads in the cluster'
          f' {args.cluster} including {workloads}. \nDo you wish to delete?'
      ):
        xpk_print('Skipping delete command.')
        return 0

  command = (
      'gcloud beta container clusters delete'
      f' {args.cluster} --project={args.project}'
      f' --location={get_cluster_location(args.project, args.cluster, args.zone)} --quiet'
  )

  return_code = run_command_with_updates(command, 'Cluster Delete')
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
      f' --project={args.project} --filter=location~"{zone_to_region(args.zone)}.*"'
  )
  return_code = run_command_with_updates(command, 'Cluster List')
  if return_code != 0:
    xpk_print(f'Cluster list request returned ERROR {return_code}')
    return 1

  return 0


def run_gke_cluster_create_command(
    args,
    gke_control_plane_version: str,
    system: SystemCharacteristics,
    release_channel: ReleaseChannel,
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
      ' --enable-dns-access'
      ' --autoscaling-profile=optimize-utilization'
      ' --labels=gke_product_type=xpk'
      f' --release-channel={release_channel.value.lower()}'
  )

  if args.gke_version:
    command += ' --no-enable-autoupgrade'

  enable_ip_alias = False

  if args.private or args.authorized_networks is not None:
    enable_ip_alias = True
    command += ' --enable-master-authorized-networks --enable-private-nodes'

  if system.accelerator_type == AcceleratorType.GPU:
    enable_ip_alias = True
    command += ' --enable-dataplane-v2 --enable-multi-networking'
  else:
    command += ' --location-policy=BALANCED --scopes=storage-full,gke-default'

    if args.enable_pathways:
      enable_ip_alias = True

  if enable_ip_alias:
    command += ' --enable-ip-alias'

  if args.enable_ray_cluster:
    command += ' --addons RayOperator'

  if args.enable_workload_identity or args.enable_gcsfuse_csi_driver:
    command += f' --workload-pool={args.project}.svc.id.goog'

  addons = []
  if args.enable_gcsfuse_csi_driver:
    addons.append('GcsFuseCsiDriver')

  if args.enable_gcpfilestore_csi_driver:
    addons.append('GcpFilestoreCsiDriver')

  if args.enable_parallelstore_csi_driver:
    addons.append('ParallelstoreCsiDriver')

  if args.enable_pd_csi_driver:
    addons.append('GcePersistentDiskCsiDriver')

  if args.enable_lustre_csi_driver:
    addons.append('LustreCsiDriver')
    if args.enable_legacy_lustre_port:
      command += ' --enable-legacy-lustre-port'

  if hasattr(args, 'enable_mtc') and args.enable_mtc:
    addons.append('HighScaleCheckpointing')

  if len(addons) > 0:
    addons_str = ','.join(addons)
    command += f' --addons={addons_str}'

  if FeatureFlags.SUPER_SLICING_ENABLED and args.super_slicing:
    command += ' --enable-slice-controller'

  if args.custom_cluster_arguments:
    command += f' {args.custom_cluster_arguments}'

  return_code = run_command_with_updates(command, 'GKE Cluster Create')
  if return_code != 0:
    xpk_print(f'GKE Cluster Create request returned ERROR {return_code}')
    return 1
  return 0


def install_storage_csis(args):
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

  if args.enable_parallelstore_csi_driver:
    update_cluster_command_code = (
        update_cluster_with_parallelstore_driver_if_necessary(args)
    )
    if update_cluster_command_code != 0:
      xpk_exit(update_cluster_command_code)

  if args.enable_pd_csi_driver:
    update_cluster_command_code = update_cluster_with_pd_driver_if_necessary(
        args
    )
    if update_cluster_command_code != 0:
      xpk_exit(update_cluster_command_code)

  if args.enable_lustre_csi_driver:
    update_cluster_command_code = (
        update_cluster_with_lustre_driver_if_necessary(args)
    )
    if update_cluster_command_code != 0:
      xpk_exit(update_cluster_command_code)


def _install_kueue(
    args,
    system: SystemCharacteristics,
    autoprovisioning_config: AutoprovisioningConfig | None,
) -> int:
  xpk_print('Enabling Kueue on the cluster')
  autoprovisioning_enabled = False
  if autoprovisioning_config:
    # Determine total resources available based on autoprovisioning max chips.
    autoprovisioning_enabled = True
    total_chips = autoprovisioning_config.maximum_chips
  else:
    # Determine total chips based on user specified topology.
    total_chips = get_total_chips_requested_from_args(args, system)
  kueue_manager = KueueManager(args.project, args.zone)
  return kueue_manager.install_or_upgrade(
      KueueConfig(
          system,
          total_chips=total_chips,
          autoprovisioning_enabled=autoprovisioning_enabled,
          num_slices=args.num_slices,
          flex=args.flex,
          memory_limit=args.memory_limit,
          cpu_limit=args.cpu_limit,
          is_pathways_cluster=args.enable_pathways,
          configure_sub_slicing=(
              FeatureFlags.SUB_SLICING_ENABLED and args.sub_slicing
          ),
          configure_super_slicing=(
              FeatureFlags.SUPER_SLICING_ENABLED and args.super_slicing
          ),
      )
  )


def prepare_gpus(system: SystemCharacteristics):
  xpk_print('Installing NCCL Plugin for cluster')
  install_nccl_code = install_nccl_on_cluster(system)
  if install_nccl_code != 0:
    xpk_exit(install_nccl_code)

  if system.device_type == H100_DEVICE_TYPE:
    xpk_print('Installing NRI device injector for cluster')
    install_nri_code = install_nri_on_cluster()
    if install_nri_code != 0:
      xpk_exit(install_nri_code)


def _log_cluster_create_telemetry(args) -> None:
  if FeatureFlags.TELEMETRY_ENABLED:
    capacity_type, _ = get_capacity_type(args)
    MetricsCollector.log_custom(
        name='cluster_create',
        metadata={
            MetricsEventMetadataKey.ZONE: args.zone,
            MetricsEventMetadataKey.SYSTEM_CHARACTERISTICS: (
                args.tpu_type if args.tpu_type else args.device_type
            ),
            MetricsEventMetadataKey.PROVISIONING_MODE: capacity_type.value,
        },
    )
