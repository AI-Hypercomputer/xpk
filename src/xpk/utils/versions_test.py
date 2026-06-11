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

import pytest
from .versions import is_gke_version_at_least


@pytest.mark.parametrize(
    "gke_version,target_version,expected",
    [
        (
            "1.35.0-gke.3065000",
            "1.35.0-gke.3065000",
            True,
        ),
        ("1.35.0-gke.3066000", "1.35.0-gke.3065000", True),
        ("1.35.1-gke.0", "1.35.0-gke.3065000", True),
        ("1.36.0-gke.100", "1.35.0-gke.3065000", True),
        ("1.35.0-gke.3064000", "1.35.0-gke.3065000", False),
        ("1.34.8-gke.1000000", "1.35.0-gke.3065000", False),
        ("invalid", "1.35.0-gke.3065000", False),
        ("1.36.0-gke.100", "1.36.0-gke.0", True),
        ("1.35.0-gke.3065000", "1.36.0-gke.0", False),
    ],
)
def test_is_gke_version_at_least(gke_version, target_version, expected):
  assert is_gke_version_at_least(gke_version, target_version) == expected
