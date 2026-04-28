"""
Copyright 2026 Google LLC

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

"""Discover PoC team configuration from the cluster's poc-team-config ConfigMap.

The ConfigMap is rendered by the Helm chart in cluster-management/poc/chart
from a single values.yaml — so a cluster admin can add/remove/retune teams
without any xpk code change.

Callers should have run `get_cluster_credentials(args)` (or otherwise set up
kubectl) before calling into this module.
"""

import difflib
import json

from . import local_cache
from .commands import run_command_for_value

CONFIG_CM_NAMESPACE = "kueue-system"
CONFIG_CM_NAME      = "poc-team-config"
CONFIG_CM_KEY       = "config.json"


def fetch_poc_config() -> dict | None:
  """Return the parsed ConfigMap payload, or None if unavailable/malformed.

  On success, refreshes ~/.xpk/poc-cache/<context>.json as a side effect so
  that argcomplete and did-you-mean suggestions work even when the cluster
  isn't reachable.
  """
  cmd = f'kubectl get configmap -n {CONFIG_CM_NAMESPACE} {CONFIG_CM_NAME} -o json'
  rc, out = run_command_for_value(cmd, task=cmd, quiet=True)
  if rc != 0 or not out:
    return None
  try:
    cm = json.loads(out)
  except json.JSONDecodeError:
    return None
  raw = (cm.get('data') or {}).get(CONFIG_CM_KEY)
  if not raw:
    return None
  try:
    cfg = json.loads(raw)
  except json.JSONDecodeError:
    return None
  ctx = local_cache.current_context()
  if ctx:
    local_cache.write(ctx, cfg)
  return cfg


def suggest(user_input: str, candidates: list[str], limit: int = 3) -> list[str]:
  """Return up to `limit` closest matches for an unknown value."""
  return difflib.get_close_matches(user_input, candidates, n=limit, cutoff=0.5)


def available_teams(cfg: dict) -> list[str]:
  return sorted((cfg.get('teams') or {}).keys())


def available_value_classes(cfg: dict) -> list[str]:
  return list(cfg.get('valueClasses') or [])


def resolve_team(cfg: dict, team: str) -> tuple[str, str, str]:
  """Return (namespace, local_queue, priority_class) for the team.

  Raises KeyError with a listing of available teams if not found.
  """
  teams = cfg.get('teams') or {}
  if team not in teams:
    raise KeyError(
        f'--team={team!r} not found on this cluster. '
        f'Available teams: {", ".join(available_teams(cfg)) or "<none>"}'
    )
  t = teams[team]
  return (t['namespace'], t['localQueue'], t['priorityClass'])


def max_k8s_workload_name_len(cfg: dict, namespace: str) -> int:
  """Max safe JobSet name length = sliceName.charLimit - fixedOverhead - len(ns).

  Defaults match the super-slice admission controller constraint (49 total,
  26 fixed overhead from prefixes/suffixes).
  """
  sn = cfg.get('sliceName') or {}
  char_limit = int(sn.get('charLimit', 49))
  fixed      = int(sn.get('fixedOverhead', 26))
  return char_limit - fixed - len(namespace)
