"""
Copyright 2025 Google LLC

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
from xpk.parser.storage import set_storage_parser

DEFAULT_ATTACH_ARGUMENTS = (
    "attach test-storage --cluster test-cluster --zone test-zone"
    " --project test-project --mount-point test-mount-point"
    " --readonly false --auto-mount true"
)

DEFAULT_LUSTRE_ATTACH_ARGUMENTS = (
    DEFAULT_ATTACH_ARGUMENTS + " --type lustre --manifest test-manifest"
)


def test_cluster_create_enable_lustre_legacy_port_is_false_by_default():
  parser = argparse.ArgumentParser()

  set_storage_parser(parser)
  args = parser.parse_args(DEFAULT_LUSTRE_ATTACH_ARGUMENTS.split())

  assert args.enable_legacy_lustre_port is False


def test_cluster_create_enable_lustre_legacy_port_can_be_set():
  parser = argparse.ArgumentParser()
  set_storage_parser(parser)
  args = parser.parse_args(
      DEFAULT_LUSTRE_ATTACH_ARGUMENTS.split() + ["--enable-legacy-lustre-port"]
  )

  assert args.enable_legacy_lustre_port is True
