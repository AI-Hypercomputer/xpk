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

from ..commands.kind import (
    cluster_create,
    cluster_delete,
    cluster_list,
)
from .common import add_global_arguments
from .validators import name_type


def set_kind_parser(kind_parser):
  cluster_subcommands = kind_parser.add_subparsers(
      title='kind subcommands',
      dest='xpk_kind_subcommands',
      help=(
          'These are commands related to kind management. Look at help for'
          ' specific subcommands for more details.'
      ),
  )

  ### "cluster create" command parser ###
  cluster_create_parser = cluster_subcommands.add_parser(
      'create', help='Create local clusters.'
  )

  ### Optional Arguments
  cluster_create_parser.add_argument(
      '--cluster',
      type=name_type,
      default='kind',
      help=(
          'The name of the cluster. Will be used as the prefix for internal'
          ' objects in the cluster.'
      ),
      required=False,
  )

  cluster_create_parser.add_argument(
      '--k8s-version',
      type=str,
      default='',
      help='The Kubernetes version of the cluster.',
      required=False,
  )

  add_global_arguments(cluster_create_parser)
  cluster_create_parser.set_defaults(func=cluster_create)

  ### "cluster delete" command parser ###
  cluster_delete_parser = cluster_subcommands.add_parser(
      'delete',
      help='Delete cloud clusters.',
  )

  cluster_delete_required_arguments = cluster_delete_parser.add_argument_group(
      'Required Arguments',
      'Arguments required for cluster delete.',
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
  add_global_arguments(cluster_delete_parser)
  cluster_delete_parser.set_defaults(func=cluster_delete)

  # "cluster list" command parser.
  cluster_list_parser = cluster_subcommands.add_parser(
      'list', help='List cloud clusters.'
  )

  ### Optional Arguments
  add_global_arguments(cluster_list_parser)
  cluster_list_parser.set_defaults(func=cluster_list)
