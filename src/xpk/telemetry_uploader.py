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

import sys
import os
import requests
import json

file_path = sys.argv[1]
if os.path.exists(file_path):
  with open(file_path, mode="r", encoding="utf-8") as file:
    kwargs = json.load(file)
    response = requests.request(**kwargs)
    print(f"Telemetry upload finished with {response.status_code} status code")

  os.remove(file_path)
