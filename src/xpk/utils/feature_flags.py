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


def _get_boolean_flag(flag: str, default: bool) -> bool:
  experiment_value = os.getenv(flag, "").lower()
  if experiment_value in ["true", "false"]:
    return experiment_value == "true"

  xpk_tester = os.getenv("XPK_TESTER", "").lower() == "true"
  return xpk_tester or default


class _FeatureFlags:
  SUB_SLICING_ENABLED = _get_boolean_flag("SUB_SLICING_ENABLED", default=False)
  TELEMETRY_ENABLED = _get_boolean_flag("TELEMETRY_ENABLED", default=False)
  SUPER_SLICING_ENABLED = _get_boolean_flag(
      "SUPER_SLICING_ENABLED", default=False
  )


FeatureFlags = _FeatureFlags()
