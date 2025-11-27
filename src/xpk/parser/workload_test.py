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
from xpk.parser.workload import set_workload_create_parser


def test_workload_create_parses():
  parser = argparse.ArgumentParser()

  set_workload_create_parser(parser)
  args = parser.parse_args([
      "--cluster",
      "test-cluster",
      "--command",
      "python3",
      "--workload",
      "test",
      "--tpu-type",
      "tpu7x-2",
  ])

  assert args
