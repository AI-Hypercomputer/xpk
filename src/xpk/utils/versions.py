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

import enum
from packaging.version import Version, InvalidVersion


class ReleaseChannel(enum.Enum):
  """
  Represents the GKE cluster release channels.

  See: https://cloud.google.com/kubernetes-engine/docs/concepts/release-channels
  """

  RELEASE_CHANNEL_UNSPECIFIED = "RELEASE_CHANNEL_UNSPECIFIED"
  RAPID = "RAPID"
  REGULAR = "REGULAR"
  STABLE = "STABLE"
  EXTENDED = "EXTENDED"


def is_gke_version_at_least(
    gke_version: str,
    target_version: str,
) -> bool:
  """Checks if a GKE version string is at least the target GKE version.

  Normalizes '-' to '+' in GKE version strings (e.g. 1.35.0-gke.3065000 ->
  1.35.0+gke.3065000) to ensure robust comparison under PEP 440.

  Args:
    gke_version: The GKE version string to check.
    target_version: The target GKE version string.

  Returns:
    True if gke_version >= target_version, False otherwise.
  """
  try:
    normalized_gke = gke_version.replace("-", "+")
    normalized_target = target_version.replace("-", "+")
    return Version(normalized_gke) >= Version(normalized_target)
  except (InvalidVersion, AttributeError):
    return False
