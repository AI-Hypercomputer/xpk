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

xpk_cfg = XpkConfig()


def set_config(args):
  xpk_cfg.set(args.set_config_args[0], args.set_config_args[1])


def get_config(args):
  value = xpk_cfg.get(args.get_config_key[0])
  xpk_print(value)
