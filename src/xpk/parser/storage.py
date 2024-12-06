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

from ..commands.storage import storage_attach, storage_delete, storage_list, storage_create
from .common import add_shared_arguments


def set_storage_parser(storage_parser: argparse.ArgumentParser) -> None:
  storage_subcommands = storage_parser.add_subparsers(
      title='storage subcommands',
      dest='xpk_storage_subcommands',
      help=(
          'These are commands related to storage management. Look at help for'
          ' specific subcommands for more details.'
      ),
  )
  add_storage_attach_parser(storage_subcommands)
  add_storage_list_parser(storage_subcommands)
  add_storage_delete_parser(storage_subcommands)
  add_storage_create_parser(storage_subcommands)


def add_storage_attach_parser(
    storage_subcommands_parser: argparse.ArgumentParser,
) -> None:

  storage_attach_parser: argparse.ArgumentParser = (
      storage_subcommands_parser.add_parser(
          'attach', help='attach XPK Storage.'
      )
  )
  storage_attach_parser.set_defaults(func=storage_attach)
  req_args = storage_attach_parser.add_argument_group(
      'Required Arguments',
      'Arguments required for storage attach.',
  )
  add_shared_arguments(req_args)
  req_args.add_argument(
      'name',
      type=str,
      help='The name of storage',
  )
  req_args.add_argument(
      '--type',
      type=str,
      help=(
          'The type of storage. Currently supported types: ["gcsfuse",'
          ' "gcpfilestore"]'
      ),
      choices=['gcsfuse', 'gcpfilestore'],
      required=True,
  )
  req_args.add_argument(
      '--cluster',
      type=str,
      required=True,
  )
  req_args.add_argument(
      '--auto-mount', type=lambda v: v.lower() == 'true', required=True
  )
  req_args.add_argument(
      '--mount-point',
      type=str,
      required=True,
  )
  req_args.add_argument(
      '--readonly', type=lambda v: v.lower() == 'true', required=True
  )

  req_args.add_argument(
      '--manifest',
      type=str,
      required=True,
  )


def add_storage_create_parser(
    storage_subcommands_parser: argparse.ArgumentParser,
) -> None:
  storage_create_parser: argparse.ArgumentParser = (
      storage_subcommands_parser.add_parser(
          'create', help='create XPK Storage.'
      )
  )
  storage_create_parser.set_defaults(func=storage_create)
  req_args = storage_create_parser.add_argument_group(
      'Required Arguments',
      'Arguments required for storage create.',
  )
  add_shared_arguments(req_args)
  req_args.add_argument(
      'name',
      type=str,
      help='The name of storage',
  )
  req_args.add_argument(
      '--vol', type=str, help='The name of the volume to create', required=True
  )
  req_args.add_argument(
      '--size',
      type=str,
      help=(
          'The size of the volume to create in gigabytes or terabytes. If no'
          ' unit is specified, gigabytes are assumed.'
      ),
      required=True,
  )
  req_args.add_argument(
      '--tier',
      type=str,
      help='The tier of the filestore to create',
      required=True,
  )

  req_args.add_argument(
      '--type',
      type=str,
      help='The type of storage. Currently supported types: [ "gcpfilestore"]',
      choices=['gcpfilestore'],
      required=True,
  )
  req_args.add_argument(
      '--cluster',
      type=str,
      required=True,
  )
  req_args.add_argument(
      '--auto-mount', type=lambda v: v.lower() == 'true', required=True
  )
  req_args.add_argument(
      '--mount-point',
      type=str,
      required=True,
  )
  req_args.add_argument(
      '--readonly', type=lambda v: v.lower() == 'true', required=True
  )
  req_args.add_argument('--manifest', type=str, required=True)


def add_storage_list_parser(
    storage_subcommands_parser: argparse.ArgumentParser,
):
  storage_list_parser: argparse.ArgumentParser = (
      storage_subcommands_parser.add_parser('list', help='List XPK Storages.')
  )
  storage_list_parser.set_defaults(func=storage_list)
  add_shared_arguments(storage_list_parser)
  req_args = storage_list_parser.add_argument_group(
      'Required Arguments',
      'Arguments required for storage list.',
  )
  req_args.add_argument(
      '--cluster',
      type=str,
  )


def add_storage_delete_parser(
    storage_subcommands_parser: argparse.ArgumentParser,
):
  storage_delete_parser: argparse.ArgumentParser = (
      storage_subcommands_parser.add_parser(
          'delete', help='Delete XPK Storage.'
      )
  )
  storage_delete_parser.set_defaults(func=storage_delete)
  add_shared_arguments(storage_delete_parser)

  req_args = storage_delete_parser.add_argument_group(
      'Required Arguments',
      'Arguments required for storage delete.',
  )
  req_args.add_argument('name', type=str)
  req_args.add_argument('--cluster', type=str, required=True)
