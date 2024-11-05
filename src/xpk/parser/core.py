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

import argparse

from ..utils.console import xpk_print
from .cluster import set_cluster_parser
from .inspector import set_inspector_parser
from .workload import set_workload_parsers
from .batch import set_batch_parser
from .info import set_info_parser


def set_parser(parser: argparse.ArgumentParser):
  xpk_subcommands = parser.add_subparsers(
      title="xpk subcommands", dest="xpk_subcommands", help="Top level commands"
  )
  workload_parser = xpk_subcommands.add_parser(
      "workload", help="commands around workload management"
  )
  cluster_parser = xpk_subcommands.add_parser(
      "cluster",
      help="Commands around creating, deleting, and viewing clusters.",
  )
  inspector_parser = xpk_subcommands.add_parser(
      "inspector",
      help="commands around investigating workload, and Kueue failures.",
  )
  info_parser = xpk_subcommands.add_parser(
      "info", help="commands around listing kueue clusterqueues and localqueues"
  )

  batch_parser = xpk_subcommands.add_parser(
      "batch",
      help="Run batch job.",
  )

  def default_subcommand_function(
      _args,
  ) -> int:  # args is unused, so pylint: disable=invalid-name
    """Default subcommand function.

    Args:
      _args: user provided arguments for running the command.

    Returns:
      0 if successful and 1 otherwise.
    """
    xpk_print("Welcome to XPK! See below for overall commands:", flush=True)
    parser.print_help()
    cluster_parser.print_help()
    workload_parser.print_help()
    batch_parser.print_help()
    info_parser.print_help()
    return 0

  parser.set_defaults(func=default_subcommand_function)
  workload_parser.set_defaults(func=default_subcommand_function)
  cluster_parser.set_defaults(func=default_subcommand_function)
  batch_parser.set_defaults(func=default_subcommand_function)
  info_parser.set_defaults(func=default_subcommand_function)

  set_workload_parsers(workload_parser=workload_parser)
  set_cluster_parser(cluster_parser=cluster_parser)
  set_inspector_parser(inspector_parser=inspector_parser)
  set_batch_parser(batch_parser=batch_parser)
  set_info_parser(info_parser=info_parser)
