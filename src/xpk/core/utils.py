"""
Copyright 2023 Google LLC

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

import urllib.request
from urllib.error import ContentTooShortError
import os
from ..utils import xpk_print, xpk_exit


def download_files_from_github_into_dir(
    path: str, urls: list[tuple[str, str]]
) -> None:
  for url, fn in urls:
    target = os.path.join(path, fn)
    try:
      urllib.request.urlretrieve(url, target)
    except ContentTooShortError as e:
      xpk_print(f'downloading kjob CRD {fn} failed due to {e.content}')
      xpk_exit(1)
