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

from ..utils import  xpk_exit
from ..core.kueue import execeute_kueuectl_list_clusterqueues, execeute_kueuectl_list_localqueues

def info_localqueues(args) -> None:
  code = execeute_kueuectl_list_localqueues(args)
  if code != 0:
    xpk_exit(code)
  return


def info_clustersqueues(args) -> None:
  code = execeute_kueuectl_list_clusterqueues(args)
  if code != 0:
    xpk_exit(code)
  return