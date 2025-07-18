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

from argparse import ArgumentParser

from ..commands.cluster import (
    cluster_adapt,
    cluster_cacheimage,
    cluster_create,
    cluster_create_pathways,
    cluster_create_ray_cluster,
    cluster_delete,
    cluster_describe,
    cluster_list,
)
from ..commands.config import xpk_cfg
from ..core.config import CFG_BUCKET_KEY
from ..core.vertex import DEFAULT_VERTEX_TENSORBOARD_NAME
from .common import add_shared_arguments
from .validators import name_type


def set_cluster_parser(cluster_parser: ArgumentParser):
  cluster_subcommands = cluster_parser.add_subparsers(
      title='cluster subcommands',
      dest='xpk_cluster_subcommands',
      help=(
          'These are commands related to cluster management. Look at help for'
          ' specific subcommands for more details.'
      ),
  )

  cluster_create_parser = cluster_subcommands.add_parser(
      'create', help='Create cloud clusters.'
  )
  cluster_create_pathways_parser = cluster_subcommands.add_parser(
      'create-pathways',
      help='Create Pathways-on-Cloud clusters.',
  )
  cluster_create_ray_cluster_parser = cluster_subcommands.add_parser(
      'create-ray',
      help='Create RayCluster',
  )
  cluster_delete_parser = cluster_subcommands.add_parser(
      'delete',
      help='Delete cloud clusters.',
  )
  cluster_cacheimage_parser = cluster_subcommands.add_parser(
      'cacheimage',
      help='Cache image.',
  )
  cluster_describe_parser = cluster_subcommands.add_parser(
      'describe',
      help='Describe a cluster.',
  )
  cluster_list_parser = cluster_subcommands.add_parser(
      'list', help='List cloud clusters.'
  )
  cluster_adapt_parser = cluster_subcommands.add_parser(
      'adapt', help='Adapt an existing cluster for XPK.'
  )

  set_cluster_create_parser(cluster_create_parser)
  set_cluster_create_pathways_parser(cluster_create_pathways_parser)
  set_cluster_create_ray_parser(cluster_create_ray_cluster_parser)
  set_cluster_delete_parser(cluster_delete_parser)
  set_cluster_cacheimage_parser(cluster_cacheimage_parser)
  set_cluster_describe_parser(cluster_describe_parser)
  set_cluster_list_parser(cluster_list_parser)
  set_cluster_adapt_parser(cluster_adapt_parser)


def set_cluster_create_parser(cluster_create_parser: ArgumentParser):
  ### Required arguments specific to "cluster create"
  cluster_create_required_arguments = cluster_create_parser.add_argument_group(
      'Required Arguments', 'Arguments required for cluster create.'
  )
  add_shared_cluster_create_required_arguments(
      cluster_create_required_arguments
  )

  cluster_device_group = (
      cluster_create_required_arguments.add_mutually_exclusive_group(
          required=True
      )
  )
  cluster_device_group.add_argument(
      '--tpu-type',
      type=str,
      default=None,
      help='The tpu type to use, v5litepod-16, etc.',
  )
  cluster_device_group.add_argument(
      '--device-type',
      type=str,
      default=None,
      help=(
          'The device type to use (can be tpu or gpu or cpu), v5litepod-16,'
          ' h100-80gb-8, n2-standard-32-4 etc.'
      ),
  )

  ### Optional arguments specific to "cluster create"
  cluster_create_optional_arguments = cluster_create_parser.add_argument_group(
      'Optional Arguments', 'Arguments optional for cluster create.'
  )
  add_shared_cluster_create_optional_arguments(
      cluster_create_optional_arguments
  )
  cluster_create_optional_arguments.add_argument(
      '--cluster-state-gcs-bucket',
      type=str,
      default=xpk_cfg.get(CFG_BUCKET_KEY),
      help='The name of the bucket to store cluster state.',
      required=False,
  )
  cluster_create_optional_arguments.add_argument(
      '--num-nodes',
      type=int,
      default=2,
      help='The number of nodes for a cluster, defaults to 2.',
      required=False,
  )
  cluster_create_optional_arguments.add_argument(
      '--enable-pathways',
      action='store_true',
      help=(
          'Please use `xpk cluster create-pathways` instead to'
          ' enable cluster to accept Pathways workloads.'
      ),
  )

  autoprovisioning_arguments = cluster_create_parser.add_argument_group(
      'Autoprovisioning Arguments',
      'Optional arguments for enabling autoprovisioning.',
  )
  add_autoprovisioning_arguments(autoprovisioning_arguments)

  ### Capacity arguments specific to "cluster create"
  cluster_create_capacity_arguments = cluster_create_parser.add_argument_group(
      'Capacity Arguments', 'Arguments related to capacity for cluster create.'
  )
  add_shared_cluster_create_capacity_arguments(
      cluster_create_capacity_arguments
  )

  ### Tensorboard arguments specific to "cluster create"
  cluster_create_tensorboard_arguments = (
      cluster_create_parser.add_argument_group(
          'Optional Vertex AI Tensorboard Arguments',
          'Arguments for creating Vertex AI Tensorboard in cluster create.',
      )
  )
  add_shared_cluster_create_tensorboard_arguments(
      cluster_create_tensorboard_arguments
  )

  ### MTC arguments specific to "cluster create"
  cluster_create_mtc_arguments = cluster_create_parser.add_argument_group(
      'Optional MTC Arguments',
      'Arguments for configuring MTC in cluster create.',
  )
  add_shared_cluster_create_mtc_arguments(cluster_create_mtc_arguments)
  cluster_create_parser.set_defaults(func=cluster_create)


def set_cluster_create_pathways_parser(
    cluster_create_pathways_parser: ArgumentParser,
):
  ### Required arguments specific to "cluster create-pathways"
  cluster_create_pathways_required_arguments = (
      cluster_create_pathways_parser.add_argument_group(
          'Required Arguments',
          'Arguments required for cluster create-pathways.',
      )
  )
  add_shared_cluster_create_required_arguments(
      cluster_create_pathways_required_arguments
  )
  cluster_create_pathways_required_arguments.add_argument(
      '--tpu-type',
      type=str,
      default=None,
      help='The tpu type to use, v5litepod-16, etc.',
  )

  ### Optional arguments specific to "cluster create-pathways"
  cluster_create_pathways_optional_arguments = (
      cluster_create_pathways_parser.add_argument_group(
          'Optional Arguments',
          'Arguments optional for cluster create-pathways.',
      )
  )
  add_shared_cluster_create_optional_arguments(
      cluster_create_pathways_optional_arguments
  )

  ### Capacity arguments specific to "cluster create-pathways"
  cluster_create_pathways_capacity_arguments = (
      cluster_create_pathways_parser.add_argument_group(
          'Capacity Arguments',
          'Arguments related to capacity for cluster create-pathways.',
      )
  )
  add_shared_cluster_create_capacity_arguments(
      cluster_create_pathways_capacity_arguments
  )

  ### Tensorboard arguments specific to "cluster create-pathways"
  cluster_create_pathways_tensorboard_arguments = cluster_create_pathways_parser.add_argument_group(
      'Optional Vertex AI Tensorboard Arguments',
      'Arguments for creating Vertex AI Tensorboard in cluster'
      ' create-pathways.',
  )
  add_shared_cluster_create_tensorboard_arguments(
      cluster_create_pathways_tensorboard_arguments
  )

  ### MTC arguments specific to "cluster create"
  cluster_create_mtc_arguments = (
      cluster_create_pathways_parser.add_argument_group(
          'Optional MTC Arguments',
          'Arguments for configuring MTC in cluster create.',
      )
  )
  add_shared_cluster_create_mtc_arguments(cluster_create_mtc_arguments)
  cluster_create_pathways_parser.set_defaults(func=cluster_create_pathways)


def set_cluster_create_ray_parser(cluster_create_ray_parser: ArgumentParser):
  ### Required arguments specific to "cluster create-ray"
  cluster_create_ray_required_arguments = (
      cluster_create_ray_parser.add_argument_group(
          'Required Arguments', 'Arguments required for cluster create-ray.'
      )
  )
  add_shared_cluster_create_required_arguments(
      cluster_create_ray_required_arguments
  )
  cluster_create_ray_required_arguments.add_argument(
      '--tpu-type',
      type=str,
      default=None,
      help='The tpu type to use, v5litepod-16, etc.',
      required=True,
  )
  # TODO(bzmarke): Add --device-type to support GPU/CPU
  cluster_create_ray_required_arguments.add_argument(
      '--ray-version',
      type=str,
      default=None,
      help="The Ray version to use, e.g. '2.38.0'",
      required=True,
  )

  ### Optional arguments specific to "cluster create-ray"
  cluster_create_ray_optional_arguments = (
      cluster_create_ray_parser.add_argument_group(
          'Optional Arguments', 'Arguments optional for cluster create-ray.'
      )
  )
  add_shared_cluster_create_optional_arguments(
      cluster_create_ray_optional_arguments
  )
  cluster_create_ray_optional_arguments.add_argument(
      '--enable-pathways',
      action='store_true',
      help=(
          'DEPRECATING SOON!!! Please use `xpk cluster create-pathways`.'
          ' Enable cluster to accept Pathways workloads.'
      ),
  )

  ### Capacity arguments specific to "cluster create-ray"
  cluster_create_ray_capacity_arguments = (
      cluster_create_ray_parser.add_argument_group(
          'Capacity Arguments',
          'Arguments related to capacity for cluster create-ray.',
      )
  )
  add_shared_cluster_create_capacity_arguments(
      cluster_create_ray_capacity_arguments
  )

  ### Tensorboard arguments specific to "cluster create-ray"
  cluster_create_ray_tensorboard_arguments = (
      cluster_create_ray_parser.add_argument_group(
          'Optional Vertex AI Tensorboard Arguments',
          'Arguments for creating Vertex AI Tensorboard in cluster create-ray.',
      )
  )
  add_shared_cluster_create_tensorboard_arguments(
      cluster_create_ray_tensorboard_arguments
  )

  ### MTC arguments specific to "cluster create"
  cluster_create_mtc_arguments = cluster_create_ray_parser.add_argument_group(
      'Optional MTC Arguments',
      'Arguments for configuring MTC in cluster create.',
  )
  add_shared_cluster_create_mtc_arguments(cluster_create_mtc_arguments)
  cluster_create_ray_parser.set_defaults(func=cluster_create_ray_cluster)


def set_cluster_delete_parser(cluster_delete_parser: ArgumentParser):
  cluster_delete_required_arguments = cluster_delete_parser.add_argument_group(
      'Required Arguments',
      'Arguments required for cluster delete.',
  )
  cluster_delete_optional_arguments = cluster_delete_parser.add_argument_group(
      'Optional Arguments', 'Arguments optional for cluster delete.'
  )

  ### Required arguments
  cluster_delete_required_arguments.add_argument(
      '--cluster',
      type=name_type,
      default=None,
      help='The name of the cluster to be deleted.',
      required=True,
  )

  ### Optional Arguments
  cluster_delete_optional_arguments.add_argument(
      '--cluster-state-gcs-bucket',
      type=str,
      default=xpk_cfg.get(CFG_BUCKET_KEY),
      help='The name of the bucket to store cluster state.',
      required=False,
  )
  add_shared_arguments(cluster_delete_optional_arguments)
  cluster_delete_optional_arguments.add_argument(
      '--force',
      action='store_true',
      help=(
          'Forces cluster deletion command to run without additional approval.'
      ),
  )

  cluster_delete_parser.set_defaults(func=cluster_delete)


def set_cluster_cacheimage_parser(cluster_cacheimage_parser: ArgumentParser):
  cluster_cacheimage_required_arguments = (
      cluster_cacheimage_parser.add_argument_group(
          'Required Arguments',
          'Arguments required for cluster cacheimage.',
      )
  )

  cluster_cacheimage_group = (
      cluster_cacheimage_parser.add_mutually_exclusive_group(required=True)
  )

  ### Device Type Argument
  cluster_cacheimage_group.add_argument(
      '--tpu-type',
      type=str,
      default=None,
      help='The tpu type to cache images on, v5litepod-16, etc.',
  )
  cluster_cacheimage_group.add_argument(
      '--device-type',
      type=str,
      default=None,
      help=(
          'The device type to cache images on (can be tpu or gpu),'
          ' v5litepod-16, h100-80gb-8, etc.'
      ),
  )

  ### Required arguments
  cluster_cacheimage_required_arguments.add_argument(
      '--cluster',
      type=name_type,
      default=None,
      help='The name of the cluster to cache the image.',
      required=True,
  )
  cluster_cacheimage_required_arguments.add_argument(
      '--docker-image',
      type=str,
      default=None,
      help='The docker-image to cache.',
      required=True,
  )

  ### Optional Arguments
  cluster_cacheimage_optional_arguments = (
      cluster_cacheimage_parser.add_argument_group(
          'Optional Arguments', 'Arguments optional for cluster cacheimage.'
      )
  )
  add_shared_arguments(cluster_cacheimage_optional_arguments)
  cluster_cacheimage_optional_arguments.add_argument(
      '--cache-key',
      type=str,
      default='containerimage',
      help='The key to cache the docker image under.',
      required=False,
  )

  cluster_cacheimage_parser.set_defaults(func=cluster_cacheimage)


def set_cluster_describe_parser(cluster_describe_parser: ArgumentParser):
  ### Required arguments
  cluster_describe_required_arguments = (
      cluster_describe_parser.add_argument_group(
          'Required Arguments',
          'Arguments required for cluster describe.',
      )
  )
  cluster_describe_required_arguments.add_argument(
      '--cluster',
      type=name_type,
      default=None,
      help='The name of the cluster to be describe.',
      required=True,
  )

  ### Optional Arguments
  cluster_describe_optional_arguments = (
      cluster_describe_parser.add_argument_group(
          'Optional Arguments', 'Arguments optional for cluster describe.'
      )
  )
  add_shared_arguments(cluster_describe_optional_arguments)

  cluster_describe_parser.set_defaults(func=cluster_describe)


def set_cluster_list_parser(cluster_list_parser: ArgumentParser):
  ### Optional Arguments
  cluster_list_optional_arguments = cluster_list_parser.add_argument_group(
      'Optional Arguments', 'Arguments optional for cluster list.'
  )
  add_shared_arguments(cluster_list_optional_arguments)

  cluster_list_parser.set_defaults(func=cluster_list)


def set_cluster_adapt_parser(cluster_adapt_parser: ArgumentParser):
  cluster_adapt_required_arguments = cluster_adapt_parser.add_argument_group(
      'Required Arguments',
      'Arguments required for cluster adapt.',
  )
  add_shared_cluster_create_required_arguments(cluster_adapt_required_arguments)

  cluster_adapt_device_group = (
      cluster_adapt_required_arguments.add_mutually_exclusive_group(
          required=True
      )
  )
  cluster_adapt_device_group.add_argument(
      '--tpu-type',
      type=str,
      default=None,
      help='The tpu type used on cluster, v5litepod-16, etc.',
  )
  cluster_adapt_device_group.add_argument(
      '--device-type',
      type=str,
      default=None,
      help=(
          'The device type used on cluster (can be tpu or gpu or cpu), eg.'
          ' h100-80gb-8, n2-standard-32-4 etc.'
      ),
  )

  cluster_adapt_optional_arguments = cluster_adapt_parser.add_argument_group(
      'Optional Arguments',
      'Arguments optional for cluster adapt.',
  )
  cluster_adapt_optional_arguments.add_argument(
      '--num-nodes',
      type=int,
      help='The number of nodes of a cluster.',
  )
  cluster_adapt_optional_arguments.add_argument(
      '--enable-workload-identity',
      action='store_true',
      help='Enable Workload Identity Federation on the cluster and node-pools.',
  )
  cluster_adapt_optional_arguments.add_argument(
      '--num-slices',
      type=int,
      default=1,
      help='The number of slices to run the job on, defaults to 1.',
      required=False,
  )
  add_driver_arguments(cluster_adapt_optional_arguments)
  add_shared_arguments(cluster_adapt_optional_arguments)

  cluster_adapt_capacity_arguments = cluster_adapt_parser.add_argument_group(
      'Capacity Arguments', 'Arguments related to capacity for cluster create.'
  )
  add_shared_cluster_create_capacity_arguments(cluster_adapt_capacity_arguments)

  cluster_adapt_autoprovisioning_arguments = (
      cluster_adapt_parser.add_argument_group(
          'Autoprovisioning Arguments',
          'Optional arguments for enabling autoprovisioning.',
      )
  )
  add_autoprovisioning_arguments(cluster_adapt_autoprovisioning_arguments)

  cluster_adapt_tensorboard_arguments = cluster_adapt_parser.add_argument_group(
      'Optional Vertex AI Tensorboard Arguments',
      'Arguments for creating Vertex AI Tensorboard in cluster adapt.',
  )
  add_shared_cluster_create_tensorboard_arguments(
      cluster_adapt_tensorboard_arguments
  )

  cluster_adapt_parser.set_defaults(func=cluster_adapt)


def add_autoprovisioning_arguments(parser: ArgumentParser):
  parser.add_argument(
      '--enable-autoprovisioning',
      action='store_true',
      help=(
          'Enable GKE features for autoprovisioning node pools in GKE clusters.'
      ),
  )
  parser.add_argument(
      '--autoprovisioning-min-chips',
      type=int,
      help=(
          'Optionally set the minimum autoprovisioning accelerator resources in'
          ' units of chips.By default, autoprovisioning will use the number of'
          ' resources in the cluster as the minimum, and maximum.'
      ),
  )
  parser.add_argument(
      '--autoprovisioning-max-chips',
      type=int,
      help=(
          'Optionally set the maximum autoprovisioning accelerator resources in'
          ' units of chips.By default, autoprovisioning will use the number of'
          ' resources in the cluster as the minimum, and maximum.'
      ),
  )


def add_shared_cluster_create_required_arguments(parser: ArgumentParser):
  """Add shared required arguments in cluster create and Pathways cluster create.

  Args:
    parser: cluster create argument parser or argument group
  """
  parser.add_argument(
      '--cluster',
      type=name_type,
      default=None,
      help=(
          'The name of the cluster. Will be used as the prefix for internal'
          ' objects in the cluster.'
      ),
      required=True,
  )


def add_shared_cluster_create_optional_arguments(parser: ArgumentParser):
  """Add shared optional arguments in cluster create and Pathways cluster create.

  Args:
    parser: cluster create argument parser or argument group
  """
  add_shared_arguments(parser)
  parser.add_argument(
      '--host-maintenance-interval',
      type=str,
      choices=['AS_NEEDED', 'PERIODIC'],
      default='AS_NEEDED',
      help='The maintenance policy of the cluster and respective clusters.',
  )
  parser.add_argument(
      '--gke-version',
      type=str,
      help=(
          'The GKE version of the cluster and respective clusters. The'
          ' default is determined dynamically based on RAPID channel'
          ' recommended version.'
      ),
  )
  parser.add_argument(
      '--num-slices',
      type=int,
      default=1,
      help='The number of slices to run the job on, defaults to 1.',
      required=False,
  )
  parser.add_argument(
      '--pathways-gce-machine-type',
      type=str,
      default='n2-standard-64',
      help='The CPU type for Pathways CPU nodepools',
  )
  parser.add_argument(
      '--default-pool-cpu-machine-type',
      type=str,
      default='e2-standard-16',
      help=(
          'Set the machine type within the default cpu node pool. For'
          ' regional clusters, all zones must support the machine type.'
      ),
  )
  parser.add_argument(
      '--cluster-cpu-machine-type',
      type=str,
      default='',
      help=(
          'Getting deprecated soon! Please use'
          ' --default-pool-cpu-machine-typeinstead, to denote the machine'
          ' type of the default cpu node pool. Set the machine type of other'
          ' cpu nodepools using --device-type.'
      ),
  )
  parser.add_argument(
      '--default-pool-cpu-num-nodes',
      type=int,
      default=6,
      help=(
          'Set the number of nodes within the default cpu node pool. This is'
          ' set to 6 by default. Autoscaling is enabled to scale this value'
          ' over time.'
      ),
  )
  parser.add_argument(
      '--custom-cluster-arguments',
      type=str,
      default='',
      help=(
          'Users can add their own arguments to customize their cluster'
          ' create command. Do note, these will not override already used'
          ' cluster creation arguments. e.g.'
          " --custom-cluster-arguments='--network=mtu9k --subnetwork=mtu9k'"
      ),
  )
  parser.add_argument(
      '--custom-nodepool-arguments',
      type=str,
      default='',
      help=(
          'Users can add their own arguments to customize their node pool '
          ' create command. Do note, these will not override already used'
          ' node pool creation arguments. e.g.'
          ' --custom-nodepool-arguments="--disk-size=300"'
      ),
  )
  parser.add_argument(
      '--force',
      action='store_true',
      help=(
          'Forces node pool creation and delete commands to run without'
          ' additional approval.'
      ),
  )
  parser.add_argument(
      '--custom-tpu-nodepool-arguments',
      type=str,
      default='',
      help=(
          'DEPRECATING SOON! Please use --custom-nodepool-arguments to'
          ' customize node pool create command. Do note, these will not'
          ' override already used node pool creation arguments. Example usage'
          ' --custom-tpu-nodepool-arguments="--enable-ip-alias"'
      ),
  )
  parser.add_argument(
      '--private',
      action='store_true',
      help=(
          'Creates a private GKE cluster, a VPC-native cluster in which Nodes'
          ' and Pods are isolated from the internet. If set,'
          ' master_authorized_networks will also be enabled and access to the'
          " cluster's control plane will be restricted only to current"
          " machine's IP address unless more IP ranges are authorized  by"
          ' providing --authorized-networks. This works only on creating new'
          ' clusters.'
      ),
  )
  parser.add_argument(
      '--authorized-networks',
      action='extend',
      nargs='+',
      help=(
          'Sets the provided cidrs as authorized IP ranges to access the'
          " private cluster's control plan. Access to the control plane will"
          " be provided to current machine's IP address even if"
          ' --authorized-networks is not set or it does not cover the IP'
          ' address. If set, --private is considered true and a private'
          ' cluster will be provisioned. It replaces existing authorized'
          ' networks if used with an existing private cluster.'
          ' Example usage: --authorized-networks 1.2.3.0/24 1.2.4.5/32'
      ),
  )
  parser.add_argument(
      '--enable-workload-identity',
      action='store_true',
      help='Enable Workload Identity Federation on the cluster and node-pools.',
  )
  add_driver_arguments(parser)


def add_driver_arguments(parser: ArgumentParser):
  parser.add_argument(
      '--enable-gcsfuse-csi-driver',
      action='store_true',
      help=(
          'Enable GSCFuse driver on the cluster. This enables Workload'
          ' Identity Federation. When using A3 ultra/A3 mega Workload'
          ' Identity is enabled by default.'
      ),
  )
  parser.add_argument(
      '--enable-gcpfilestore-csi-driver',
      action='store_true',
      help='Enable GCPFilestore driver on the cluster.',
  )
  parser.add_argument(
      '--enable-parallelstore-csi-driver',
      action='store_true',
      help='Enable Parallelstore CSI driver on the cluster.',
  )
  parser.add_argument(
      '--enable-pd-csi-driver',
      action='store_true',
      help='Enable PersistentDisk CSI driver on the cluster.',
  )
  parser.add_argument(
      '--enable-lustre-csi-driver',
      action='store_true',
      help='Enable Lustre CSI driver on the cluster.',
  )


def add_shared_cluster_create_tensorboard_arguments(parser: ArgumentParser):
  """Add shared tensorboard arguments in cluster create and Pathways cluster create.
  Note that this feature enables non-Pathways workloads to use tensorboard arguments
  on a Pathways cluster.

  Args:
    parser: cluster create argument parser or argument group
  """
  parser.add_argument(
      '--create-vertex-tensorboard',
      action='store_true',
      help='Set this flag to create a Tensorboard instance in Vertex AI.',
  )
  parser.add_argument(
      '--tensorboard-region',
      type=str,
      default='us-central1',
      help=(
          'The region to create Vertex Tensorboard instance in. Visit'
          ' https://cloud.google.com/vertex-ai/docs/general/locations#available-regions'
          ' to view regions supported by Vertex AI. By default, Tensorboard'
          ' instance will be created in us-central1.'
      ),
  )
  parser.add_argument(
      '--tensorboard-name',
      type=str,
      required=False,
      help=(
          'The name of Vertex Tensorboard instance to create. If not'
          ' specified, a Tensorboard instance with the name'
          f' <cluster>-{DEFAULT_VERTEX_TENSORBOARD_NAME} will be'
          ' created.'
      ),
  )


def add_shared_cluster_create_capacity_arguments(parser: ArgumentParser):
  """Add shared capacity arguments in cluster create and Pathways cluster create.

  Args:
    parser: cluster create argument parser or argument group
  """
  parser.add_argument(
      '--on-demand',
      action='store_true',
      help=(
          'Sets node pool creation to use on-demand resources.  See'
          ' `--reservation`, `--flex` or `--spot` for other capacity'
          ' types.'
      ),
  )
  parser.add_argument(
      '--reservation',
      type=str,
      help=(
          'The reservation to be used for acquiring resources in the cluster.'
          ' This will attempt to find the provided reservation. See `--spot`,'
          ' `--flex` or `--on-demand` for other capacity types.'
      ),
  )
  parser.add_argument(
      '--spot',
      action='store_true',
      help=(
          'Sets node pool creation to use spot resources. See'
          ' `--reservation`, `--flex` or `--on-demand` for other'
          ' capacity types.'
      ),
  )
  parser.add_argument(
      '--flex',
      action='store_true',
      help=(
          'Sets node pool creation to use DWS Flex Start resources. See'
          ' `--reservation`, `--on-demand` or `--spot` for other capacity'
          ' types.'
      ),
  )


def add_shared_cluster_create_mtc_arguments(parser: ArgumentParser):
  """Add shared Multi-tier Checkpointing arguments in cluster create and Pathways cluster create.

  Args:
      List of cluster create MTC arguments parsers
  """
  parser.add_argument(
      '--enable-mtc',
      action='store_true',
      help='Enable MTC on the cluster.',
  )
  parser.add_argument(
      '--mtc-ramdisk-size',
      type=str,
      default=None,
      help=(
          '(Required if --enable-mtc is true) The size of the RAM disk to be'
          ' used for multi-tier checkpointing. e.g. "64Mi" '
      ),
  )
  parser.add_argument(
      '--mtc-gcs-bucket',
      type=str,
      default=None,
      help=(
          '(Required if --enable-mtc is true) The GCS bucket to be used for'
          ' multi-tier checkpointing.'
      ),
  )
  parser.add_argument(
      '--mtc-toleration-key',
      type=str,
      default=None,
      help=(
          '(Optional) The tolerance key to be used for multi-tier'
          ' checkpointing. By default, it is set to "google.com/tpu".'
      ),
  )
