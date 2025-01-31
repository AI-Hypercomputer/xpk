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

from ..core.config import XpkConfig
from ..utils.console import xpk_print
import os

XPK_CONFIG_FILE = os.path.expanduser('~') + '/.config/xpk/config.yaml'
xpk_cfg = XpkConfig(XPK_CONFIG_FILE)


def config(args):
  if args.set:
    set_config(args.set)
  if args.get:
    get_config(args.get)


def set_config(values):
  for k, v in values.items():
    xpk_cfg.set(k, v)


def get_config(key):
  value = xpk_cfg.get(key)
  xpk_print(value)
