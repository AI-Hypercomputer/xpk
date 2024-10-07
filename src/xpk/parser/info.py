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

from ..commands.info import info

def set_info_parser(info_parser):
  info_required_arguments = info_parser.add_argument_group(
      'Required Arguments', 'Arguments required for info.'
  )

  info_required_arguments.add_argument(
    '--cluster',
    type = str,
    default = None,
    help = 'Cluster to which command applies.'
  )

  info_required_arguments.add_argument(
    '--localqueue',
    action='store_true',
    help = 'Print info about localqueue',
  )

  info_required_arguments.add_argument(
    '--clusterqueue',
    action='store_true',
    help = 'Print info about localqueue',
  )
  info_parser.set_defaults(func=info)
