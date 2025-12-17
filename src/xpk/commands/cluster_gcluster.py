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

import os

from ..utils.feature_flags import FeatureFlags
from ..utils.versions import ReleaseChannel
from ..utils.execution_context import is_dry_run
from ..core.kueue_manager import KueueConfig, KueueManager
from ..core.nap import enable_autoprovisioning_on_cluster
from ..core.scheduling import get_total_chips_requested_from_args
from ..core.system_characteristics import get_system_characteristics

from ..core.blueprint.blueprint_generator import (
    BlueprintGenerator,
    BlueprintGeneratorOutput,
    a3mega_device_type,
    a3ultra_device_type,
    a4_device_type,
    supported_device_types,
)
from ..core.capacity import get_capacity_type
from ..core.cluster import get_cluster_credentials
from ..core.commands import run_command_for_value
from ..core.docker_manager import DockerManager
from ..core.gcloud_context import zone_to_region
from ..core.gcluster_manager import GclusterManager
from ..core.remote_state.fuse_remote_state import FuseStateClient
from ..core.remote_state.remote_state_client import RemoteStateClient
from ..utils.console import xpk_exit, xpk_print
from ..utils.file import ensure_directory_exists
from ..utils.network import all_IPs_cidr
from ..utils.objects import hash_string
from ..core.capacity import get_reservation_maintenance_interval, get_reservation_placement_policy

blueprints_path = os.path.abspath('xpkclusters/blueprints')
gcluster_working_dir = os.path.abspath('xpkclusters/gcluster-out')
gcloud_cfg_path = os.path.expanduser('~/.config/gcloud')


def cluster_create(
    args, gke_control_plane_version: str, release_channel: ReleaseChannel
) -> None:
  """Function around cluster creation using Cluster toolkit.

  Args:
    args: user provided arguments for running the command.
    gke_control_plane_version: the GKE version used for the new cluster.
    release_channel:t the release channel used for the new cluster.

  Returns:
    0 if successful and 1 otherwise.
  """
  check_gcloud_authenticated()
  prepare_directories()
  region = zone_to_region(args.zone)

  # unique_name uses shortened hash string, so still name collision is possible
  unique_name = get_unique_name(args.project, region, args.cluster)
  # prefix is to prevent name collisions for blueprints and also deployments by storing them in prefix directory. Ex.: blueprints/{prefix}/cluster_name_hash
  prefix = get_prefix_path(args.project, region)
  remote_state_client = None
  if args.cluster_state_gcs_bucket is not None:
    remote_state_client = FuseStateClient(
        bucket=args.cluster_state_gcs_bucket,
        state_directory=os.path.join(blueprints_path, prefix, unique_name),
        prefix=prefix,
        cluster=args.cluster,
        deployment_name=unique_name,
    )
  gcm = prepare_gcluster_manager(remote_state_client)

  bp = generate_blueprint(
      blueprint_name=unique_name,
      args=args,
      prefix=prefix,
      gke_control_plane_version=gke_control_plane_version,
      release_channel=release_channel,
  )

  # staging: sending the blueprint file(s) to gcluster's working directory
  if is_dry_run():
    xpk_print(f'Blueprint file: {bp.blueprint_file}')
  else:
    bp_staged_path = gcm.stage_files(
        blueprint_file=bp.blueprint_file,
        blueprint_dependencies=bp.blueprint_dependencies,
        prefix=prefix,
    )
    gcm.deploy(
        blueprint_path=bp_staged_path,
        deployment_name=unique_name,
        prefix=prefix,
    )
    if args.cluster_state_gcs_bucket is not None:
      gcm.upload_state()

  get_cluster_credentials(args)

  err_code = __install_kueue(args)
  xpk_exit(err_code)


def __install_kueue(args) -> int:
  system, return_code = get_system_characteristics(args)

  if return_code > 0 or system is None:
    xpk_print('Fetching system characteristics failed!')
    return return_code

  # Provision node pools dynamically based on incoming workloads:
  # Currently autoprovisioning is not supported with Pathways.
  autoprovisioning_config = None
  if args.enable_autoprovisioning:
    xpk_print('Enabling Autoprovisioning')
    autoprovisioning_config, return_code = enable_autoprovisioning_on_cluster(
        args, system
    )
    if return_code != 0:
      return return_code

  autoprovisioning_enabled = False
  if autoprovisioning_config:
    # Determine total resources available based on autoprovisioning max chips.
    autoprovisioning_enabled = True
    total_chips = autoprovisioning_config.maximum_chips
  else:
    # Determine total chips based on user specified topology.
    total_chips = get_total_chips_requested_from_args(args, system)
  kueue_manager = KueueManager(args.project, args.zone)

  tolerations = [{
      'key': 'components.gke.io/gke-managed-components',
      'operator': 'Equal',
      'value': 'true',
      'effect': 'NoSchedule',
  }]
  kueue_manager.install_or_upgrade(
      KueueConfig(
          system,
          total_chips=total_chips,
          autoprovisioning_enabled=autoprovisioning_enabled,
          num_slices=args.num_slices,
          memory_limit=args.memory_limit,
          cpu_limit=args.cpu_limit,
          is_pathways_cluster=args.enable_pathways,
          flex=args.flex,
          configure_sub_slicing=(
              FeatureFlags.SUB_SLICING_ENABLED and args.sub_slicing
          ),
          configure_super_slicing=(
              FeatureFlags.SUPER_SLICING_ENABLED and args.super_slicing
          ),
      ),
      tolerations=tolerations,
  )
  return 0


def cluster_delete(args) -> None:
  """Function around cluster delete for the clusters created by Cluster toolkit.

  Args:
    args: user provided arguments for running the command.

  Returns:
    0 if successful and 1 otherwise.
  """
  check_gcloud_authenticated()
  prepare_directories()
  region = zone_to_region(args.zone)
  unique_name = get_unique_name(args.project, region, args.cluster)
  # prefix is to prevent name collisions for blueprints and also deployments by storing them in prefix directory. Ex.: blueprints/{prefix}/cluster_name_hash
  prefix = get_prefix_path(args.project, region)
  remote_state_client = None
  if args.cluster_state_gcs_bucket is not None:
    remote_state_client = FuseStateClient(
        bucket=args.cluster_state_gcs_bucket,
        state_directory=os.path.join(blueprints_path, prefix, unique_name),
        prefix=prefix,
        cluster=args.cluster,
        deployment_name=unique_name,
    )
  gcm = prepare_gcluster_manager(remote_state_client)

  # unique_name uses shortened hash string, so still name collision is possible
  unique_name = get_unique_name(args.project, region, args.cluster)
  # prefix is to prevent name collisions for blueprints and also deployments by storing them in prefix directory. Ex.: blueprints/{prefix}/cluster_name_hash
  prefix = get_prefix_path(args.project, region)
  if args.cluster_state_gcs_bucket is not None:
    gcm.download_state()

    bp = BlueprintGeneratorOutput(
        blueprint_file=os.path.join(blueprints_path, prefix, unique_name)
        + '.yaml',
        blueprint_dependencies=os.path.join(
            blueprints_path, prefix, unique_name
        ),
    )

    gcm.stage_files(
        blueprint_file=bp.blueprint_file,
        blueprint_dependencies=bp.blueprint_dependencies,
        prefix=prefix,
    )
  gcm.destroy_deployment(deployment_name=unique_name, prefix=prefix)

  xpk_exit(0)


def created_by_gcluster(args) -> bool:
  prepare_directories()
  region = zone_to_region(args.zone)
  unique_name = get_unique_name(args.project, region, args.cluster)
  prefix = get_prefix_path(args.project, region)
  bpg = prepare_blueprint_generator()
  return bpg.blueprint_exists(unique_name, prefix)


def get_unique_name(project_id, region, cluster_name):
  unique_string_hash = hash_string(
      input_string=f'{project_id}-{region}-{cluster_name}'.lower(), length=5
  )
  return f'{cluster_name}-{unique_string_hash}'


def get_prefix_path(project_id, region):
  return f'{project_id}-{region}'.lower()


def prepare_directories() -> None:
  ensure_directory_exists(blueprints_path)
  ensure_directory_exists(gcluster_working_dir)


def check_gcloud_authenticated():
  if not os.path.exists(gcloud_cfg_path):
    xpk_print(
        'Failed to find gcloud credential directory.'
        f' {gcloud_cfg_path} {blueprints_path} {gcluster_working_dir}'
    )
    xpk_print(
        'Please authenticate to gcloud ("gcloud auth application-default'
        ' login") and then run your command.'
    )
    xpk_exit(1)


def prepare_gcluster_manager(
    remote_state_client: RemoteStateClient | None,
) -> GclusterManager:
  dm = DockerManager(
      working_dir=gcluster_working_dir, gcloud_cfg_path=gcloud_cfg_path
  )
  dm.initialize()
  return GclusterManager(
      gcluster_command_runner=dm, remote_state_client=remote_state_client
  )


def prepare_blueprint_generator() -> BlueprintGenerator:
  return BlueprintGenerator(storage_path=blueprints_path)


def validate_state_gcs_bucket(args):
  bucket_validate_cmd = (
      f'gcloud storage buckets describe gs://{args.cluster_state_gcs_bucket}'
  )
  err_code, _ = run_command_for_value(
      bucket_validate_cmd,
      'Validate remote state bucket existence.',
  )
  if err_code != 0:
    xpk_exit(err_code)


def generate_blueprint(
    blueprint_name,
    args,
    gke_control_plane_version: str,
    release_channel: ReleaseChannel,
    prefix=None,
) -> BlueprintGeneratorOutput:
  capacity_type, return_code = get_capacity_type(args)
  if return_code != 0:
    xpk_print('Capacity type is invalid.')
    xpk_exit(return_code)

  bpg = prepare_blueprint_generator()

  if args.cluster_state_gcs_bucket is not None:
    validate_state_gcs_bucket(args)

  if args.device_type in supported_device_types:
    if args.device_type == a3mega_device_type:
      num_nodes = args.num_nodes if not args.num_nodes is None else 2

      maintenance_interval = (
          get_reservation_maintenance_interval(
              args.reservation, args.zone, args.project
          )
          if args.reservation is not None
          else 'PERIODIC'
      )
      placement_policy_name = (
          get_reservation_placement_policy(
              args.reservation, args.zone, args.project
          )
          if args.reservation is not None
          else None
      )
      placement_policy = (
          {
              'type': 'COMPACT',
              'name': placement_policy_name.split('/')[-1],
          }
          if placement_policy_name is not None
          and len(placement_policy_name) > 0
          else None
      )
      return bpg.generate_a3_mega_blueprint(
          blueprint_name=blueprint_name,
          prefix=prefix,
          cluster_name=args.cluster,
          region=zone_to_region(args.zone),
          project_id=args.project,
          zone=args.zone,
          auth_cidr=all_IPs_cidr,
          num_nodes=num_nodes,
          reservation_maintenance_interval=maintenance_interval,
          reservation_placement_policy=placement_policy,
          reservation=args.reservation if args.reservation else None,
          capacity_type=capacity_type,
          system_node_pool_machine_type=args.default_pool_cpu_machine_type,
          system_node_pool_min_node_count=args.default_pool_cpu_num_nodes,
          gcs_bucket=args.cluster_state_gcs_bucket,
          cluster_version=gke_control_plane_version,
          release_channel=release_channel,
      )
    if args.device_type == a3ultra_device_type:
      num_nodes = args.num_nodes if not args.num_nodes is None else 2
      return bpg.generate_a3_ultra_blueprint(
          blueprint_name=blueprint_name,
          prefix=prefix,
          cluster_name=args.cluster,
          region=zone_to_region(args.zone),
          project_id=args.project,
          zone=args.zone,
          auth_cidr=all_IPs_cidr,
          num_nodes=num_nodes,
          reservation=args.reservation if args.reservation else None,
          enable_filestore_csi_driver=args.enable_gcpfilestore_csi_driver,
          capacity_type=capacity_type,
          system_node_pool_machine_type=args.default_pool_cpu_machine_type,
          system_node_pool_min_node_count=args.default_pool_cpu_num_nodes,
          gcs_bucket=args.cluster_state_gcs_bucket,
          cluster_version=gke_control_plane_version,
          release_channel=release_channel,
      )
    if args.device_type == a4_device_type:
      num_nodes = args.num_nodes if not args.num_nodes is None else 2
      return bpg.generate_a4_blueprint(
          blueprint_name=blueprint_name,
          prefix=prefix,
          cluster_name=args.cluster,
          region=zone_to_region(args.zone),
          project_id=args.project,
          zone=args.zone,
          auth_cidr=all_IPs_cidr,
          num_nodes=num_nodes,
          reservation=args.reservation if args.reservation else None,
          capacity_type=capacity_type,
          system_node_pool_machine_type=args.default_pool_cpu_machine_type,
          system_node_pool_min_node_count=args.default_pool_cpu_num_nodes,
          cluster_version=gke_control_plane_version,
          release_channel=release_channel,
      )
  xpk_print('Device type is not supported.')
  xpk_exit(1)
