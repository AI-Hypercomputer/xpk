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


from ..utils import workload_name_type
from .common import add_shared_arguments

from ..utils import xpk_exit
from ..commands.info import info_clustersqueues, info_localqueues

def set_info_parser(info_parser):
  info_subcommands = info_parser.add_subparsers(
      title='info subcommands',
      dest='xpk_info_subcommands',
      help='Get Kueue localqueues and clusterqueues details.',
  )

  info_localqueues_parser = info_subcommands.add_parser(
    'localqueues', help='Get info about local queues'
  )

  info_localqueues_required_arguments = info_localqueues_parser.add_argument_group(
      'Required Arguments',
      'Arguments required for info localqueues.',
  )
  info_localqueues_optional_arguments = info_localqueues_parser.add_argument_group(
      'Optional Arguments', 'Arguments optional for info localqueues.'
  )

  info_localqueues_optional_arguments.add_argument(
    '--cluster',
    type = str,
    default = None,
    help = 'Cluster to which command applies.'
  )
  
  info_clusterqueues_parser = info_subcommands.add_parser(
    'clusterqueues', help = 'Get info about cluster queues'
  )

  info_clusterqueues_required_arguments = info_clusterqueues_parser.add_argument_group(
      'Required Arguments',
      'Arguments required for info clusterqueues.',
  )
  info_clusterqueues_optional_arguments = info_clusterqueues_parser.add_argument_group(
      'Optional Arguments', 'Arguments optional for info clusterqueues.'
  )
  info_clusterqueues_optional_arguments.add_argument(
    '--cluster',
    type = str,
    default = None,
    help = 'Cluster to which command applies.'
  )
  
  info_localqueues_parser.set_defaults(func=info_localqueues)
  info_clusterqueues_parser.set_defaults(func=info_clustersqueues)
