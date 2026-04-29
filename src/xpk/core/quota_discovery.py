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

"""Discover team-based Kueue quota configuration from a cluster ConfigMap.

xpk's `--team` / `--value-class` / `--declared-duration-minutes` flags route a
workload to a per-team Kueue namespace + ClusterQueue, with priority and slice-
name sizing derived from cluster-side config. The config (which teams exist,
their quotas, namespaces, priorities, and the JobSet-name length budget) is
read at runtime from a ConfigMap so that adding/retuning a team requires no
xpk code change.

Callers should have run `get_cluster_credentials(args)` (or otherwise set up
kubectl) before calling into this module.
"""

import difflib
import json
from dataclasses import dataclass

from . import local_cache
from .commands import run_command_for_value

CONFIG_CM_NAMESPACE = 'kueue-system'
CONFIG_CM_NAME = 'poc-team-config'  # cluster-side ConfigMap name; set by chart
CONFIG_CM_KEY = 'config.json'


@dataclass(frozen=True)
class TeamRouting:
  """Per-team Kueue routing parameters resolved from the cluster ConfigMap."""

  namespace: str
  local_queue: str
  priority_class: str


def fetch_quota_config() -> dict | None:
  """Return the parsed ConfigMap payload, or None if unavailable/malformed.

  On success, refreshes ~/.xpk/poc-cache/<context>.json as a side effect so
  that argcomplete and did-you-mean suggestions work even when the cluster
  isn't reachable.
  """
  cmd = (
      f'kubectl get configmap -n {CONFIG_CM_NAMESPACE} {CONFIG_CM_NAME} -o json'
  )
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


def suggest(
    user_input: str, candidates: list[str], limit: int = 3
) -> list[str]:
  """Return up to `limit` closest matches for an unknown value."""
  return difflib.get_close_matches(user_input, candidates, n=limit, cutoff=0.5)


def available_teams(cfg: dict) -> list[str]:
  return sorted((cfg.get('teams') or {}).keys())


def available_value_classes(cfg: dict) -> list[str]:
  return list(cfg.get('valueClasses') or [])


def resolve_team(cfg: dict, team: str) -> TeamRouting:
  """Return TeamRouting for the team.

  Raises KeyError with a listing of available teams if not found.
  """
  teams = cfg.get('teams') or {}
  if team not in teams:
    raise KeyError(
        f'--team={team!r} not found on this cluster. '
        f'Available teams: {", ".join(available_teams(cfg)) or "<none>"}'
    )
  t = teams[team]
  return TeamRouting(
      namespace=t['namespace'],
      local_queue=t['localQueue'],
      priority_class=t['priorityClass'],
  )


def max_k8s_workload_name_len(cfg: dict, namespace: str) -> int:
  """Max safe JobSet name length = sliceName.charLimit - fixedOverhead - len(ns).

  The super-slice admission controller enforces a hard length limit on the
  Slice CRD names it creates from the JobSet, of the form
  `<namespace>-<jobset-name>-slice-job-<replica-index>`. The total `charLimit`
  (49 by default) minus the `fixedOverhead` (the 26-char framing for the
  `-slice-job-N` suffix and the jobset-controller's own prefixing) minus the
  namespace length yields the budget left for the actual JobSet (and hence
  workload) name.

  These values come from the cluster ConfigMap so a cluster admin can adjust
  them without an xpk release.
  """
  sn = cfg.get('sliceName') or {}
  char_limit = int(sn.get('charLimit', 49))
  fixed = int(sn.get('fixedOverhead', 26))
  return char_limit - fixed - len(namespace)
