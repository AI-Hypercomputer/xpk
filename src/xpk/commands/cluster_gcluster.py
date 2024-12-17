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

from ..core.blueprint.blueprint_generator import BlueprintGenerator, BlueprintGeneratorOutput, supported_device_types, a3mega_device_type
from ..core.docker_manager import DockerManager
from ..core.gcluster_manager import GclusterManager
from ..core.core import zone_to_region
from ..utils.console import xpk_exit, xpk_print
from ..utils.network import all_IPs_cidr
from ..utils.file import ensure_directory_exists
from ..utils.objects import hash_string
import os

blueprints_path = os.path.abspath('xpkclusters/blueprints')
gcluster_working_dir = os.path.abspath('xpkclusters/gcluster-out')
gcloud_cfg_path = os.path.expanduser('~/.config/gcloud')


def cluster_create(args) -> None:
  """Function around cluster creation using Cluster toolkit.

  Args:
    args: user provided arguments for running the command.

  Returns:
    0 if successful and 1 otherwise.
  """
  check_gcloud_authenticated()
  prepare_directories()
  gcm = prepare_gcluster_manager()
  region = zone_to_region(args.zone)

  # unique_name uses shortened hash string, so still name collision is possible
  unique_name = get_unique_name(args.project, region, args.cluster)
  # prefix is to prevent name collisions for blueprints and also deployments by storing them in prefix directory. Ex.: blueprints/{prefix}/cluster_name_hash
  prefix = get_prefix_path(args.project, region)

  bp = generate_blueprint(blueprint_name=unique_name, args=args, prefix=prefix)

  # staging: sending the blueprint file(s) to gcluster's working directory
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

  xpk_exit(0)


def cluster_delete(args) -> None:
  """Function around cluster delete for the clusters created by Cluster toolkit.

  Args:
    args: user provided arguments for running the command.

  Returns:
    0 if successful and 1 otherwise.
  """
  check_gcloud_authenticated()
  prepare_directories()
  gcm = prepare_gcluster_manager()
  region = zone_to_region(args.zone)

  # unique_name uses shortened hash string, so still name collision is possible
  unique_name = get_unique_name(args.project, region, args.cluster)
  # prefix is to prevent name collisions for blueprints and also deployments by storing them in prefix directory. Ex.: blueprints/{prefix}/cluster_name_hash
  prefix_path = get_prefix_path(args.project, region)

  gcm.destroy_deployment(deployment_name=unique_name, prefix=prefix_path)

  xpk_exit(0)


def created_by_gcluster(args) -> bool:
  prepare_directories()
  unique_name = get_unique_name(
      args.project, zone_to_region(args.zone), args.cluster
  )
  bpg = prepare_blueprint_generator()
  return bpg.blueprint_exists(unique_name)


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
    xpk_exit(-1)


def prepare_gcluster_manager() -> GclusterManager:
  dm = DockerManager(
      working_dir=gcluster_working_dir, gcloud_cfg_path=gcloud_cfg_path
  )
  dm.initialize()
  return GclusterManager(gcluster_command_runner=dm)


def prepare_blueprint_generator() -> BlueprintGenerator:
  return BlueprintGenerator(storage_path=blueprints_path)


def generate_blueprint(
    blueprint_name, args, prefix=None
) -> BlueprintGeneratorOutput:
  validate_consumtion_args(args)
  bpg = prepare_blueprint_generator()

  if args.device_type in supported_device_types:
    if args.device_type == a3mega_device_type:
      num_nodes = args.num_nodes if not args.num_nodes is None else 2
      return bpg.generate_a3_mega_blueprint(
          blueprint_name=blueprint_name,
          prefix=prefix,
          cluster_name=args.cluster,
          region=zone_to_region(args.zone),
          project_id=args.project,
          zone=args.zone,
          auth_cidr=all_IPs_cidr,
          num_nodes=num_nodes,
          autoscaling_total_min_nodes=num_nodes,
          reservation=args.reservation if args.reservation else None,
          spot=args.spot if args.spot else False,
          system_node_pool_machine_type=args.default_pool_cpu_machine_type,
          system_node_pool_min_node_count=args.default_pool_cpu_num_nodes,
      )
  return None


def validate_consumtion_args(args):
  args_set = []
  if not args.reservation is None:
    args_set.append('--reservation')
  if not args.spot is None and args.spot:
    args_set.append('--spot')
  if not args.on_demand is None and args.on_demand:
    args_set.append('--on-demand')

  if len(args_set) > 1:
    xpk_print(
        f"Error: only one of {' or '.join(args_set)} can be set at the same"
        ' time.'
    )
    xpk_exit(-1)