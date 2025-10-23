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

import os

import ruamel.yaml

TEMPLATE_PATH = "templates"

yaml = ruamel.yaml.YAML()


def load(path: str) -> dict:
  template_path = os.path.dirname(__file__) + path
  with open(template_path, "r", encoding="utf-8") as file:
    data: dict = yaml.load(file)
  return data


def get_templates_absolute_path(templates_path: str = TEMPLATE_PATH) -> str:
  """
  Return the absolute path to the templates folder

  Args:
    templates_path: The path to the templates folder relative to the src/xpk directory
  """
  current_file_path = os.path.abspath(__file__)
  current_dir = os.path.dirname(current_file_path)
  xpk_package_dir = os.path.dirname(current_dir)
  return os.path.join(xpk_package_dir, templates_path)
