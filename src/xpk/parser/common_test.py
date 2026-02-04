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
from .common import extract_command_path, enable_flags_usage_tracking, retrieve_flags
from .core import set_parser


def test_enable_flags_usage_tracking():
  parser = argparse.ArgumentParser()
  parser.add_argument('--foo', action='store_true')
  parser.add_argument('-b', '--bar', type=str)
  subparsers = parser.add_subparsers(dest='command')
  sub_parser = subparsers.add_parser('run')
  sub_parser.add_argument('--baz', action='store_true')

  enable_flags_usage_tracking(parser)

  args = parser.parse_args(['--foo', '-b', 'dummy_val', 'run', '--baz'])

  assert retrieve_flags(args) == 'bar baz foo'


def test_extract_zero_level_nested_command():
  parser = argparse.ArgumentParser()
  set_parser(parser=parser)
  args = parser.parse_args([])
  assert extract_command_path(parser, args) == ''


def test_extract_one_level_nested_command():
  parser = argparse.ArgumentParser()
  set_parser(parser=parser)
  args = parser.parse_args(['version'])
  assert extract_command_path(parser, args) == 'version'


def test_extract_two_level_nested_command():
  parser = argparse.ArgumentParser()
  set_parser(parser=parser)
  args = parser.parse_args(['cluster', 'list'])
  assert extract_command_path(parser, args) == 'cluster list'


def test_extract_two_level_nested_command_with_flags():
  parser = argparse.ArgumentParser()
  set_parser(parser=parser)
  args = parser.parse_args(
      ['cluster', 'list', '--project=abc', '--zone=us-central1-a']
  )
  assert extract_command_path(parser, args) == 'cluster list'
