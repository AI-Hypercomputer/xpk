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
import os
import shlex
from dataclasses import dataclass

from . import local_cache
from .commands import run_command_for_value
from .config import TEAM_CONFIGMAP_NAME_KEY, get_config
from ..utils.console import xpk_exit, xpk_print

CONFIG_CM_NAMESPACE = 'kueue-system'
DEFAULT_CONFIG_CM_NAME = 'team-quota-config'
CONFIG_CM_KEY = 'config.json'


def _configmap_name() -> str:
  """Resolve the cluster-side ConfigMap name.

  Operators with a pre-existing ConfigMap under a different name (e.g.
  legacy deployments where it was called `poc-team-config`) can override
  the default with `xpk config set team-configmap-name <name>` instead of
  renaming the ConfigMap on the cluster.
  """
  override = get_config().get(TEAM_CONFIGMAP_NAME_KEY)
  return override or DEFAULT_CONFIG_CM_NAME


@dataclass(frozen=True)
class TeamRouting:
  """Per-team Kueue routing parameters resolved from the cluster ConfigMap."""

  namespace: str
  local_queue: str
  priority_class: str


def _dry_run_quota_cfg() -> dict | None:
  """Read the team-quota ConfigMap payload from the env var, if set.

  Recipes and `--dry-run` invocations can set XPK_TEAM_QUOTA_DRY_RUN_CONFIG
  to a JSON object representing the contents of `data["config.json"]` from
  the cluster ConfigMap. Lets reviewers / docs demonstrate the team-routing
  path without a live cluster (mirrors DRY_RUN_RESERVATION_SUB_BLOCKS).
  """
  raw = os.getenv('XPK_TEAM_QUOTA_DRY_RUN_CONFIG')
  if not raw:
    return None
  try:
    cfg = json.loads(raw)
  except json.JSONDecodeError:
    return None
  return cfg if isinstance(cfg, dict) else None


def fetch_quota_config() -> dict | None:
  """Return the parsed ConfigMap payload, or None if unavailable/malformed.

  Honors XPK_TEAM_QUOTA_DRY_RUN_CONFIG first so recipes can demonstrate the
  team-routing path without a cluster. Otherwise reads the live ConfigMap
  via kubectl and refreshes ~/.xpk/quota-cache/<context>.json as a side
  effect (used by argcomplete + did-you-mean suggestions).

  The ConfigMap name defaults to `team-quota-config`; operators with a
  pre-existing differently-named ConfigMap can override via
  `xpk config set team-configmap-name <name>`.
  """
  dry = _dry_run_quota_cfg()
  if dry is not None:
    return dry
  # cm_name comes from xpk config (user-controlled). run_command_for_value
  # invokes the command via shell=True, so quote it to prevent shell-meta
  # interpolation if the config value contains spaces / `;` / `&` / etc.
  cm_name = shlex.quote(_configmap_name())
  cmd = f'kubectl get configmap -n {CONFIG_CM_NAMESPACE} {cm_name} -o json'
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
  if not isinstance(cfg, dict):
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


def load_quota_cfg(args) -> dict | None:
  """Fetch + validate the team-quota ConfigMap once per invocation.

  Returns None when --team is unset (so the upstream non-team-routing path
  is preserved). Caches the result on `args.quota_cfg` so a single
  invocation never hits the cluster twice.

  Robust against unit-test code that passes a MagicMock for args:
  args.team must be a non-empty *string*, not just truthy.
  """
  team = getattr(args, 'team', None)
  if not isinstance(team, str) or not team.strip():
    return None
  cached = getattr(args, 'quota_cfg', None)
  if isinstance(cached, dict):
    return cached
  cfg = fetch_quota_config()
  if cfg is None:
    cm_name = _configmap_name()
    xpk_print(
        f'ERROR: --team={args.team!r} requires the team-quota ConfigMap'
        f' "{CONFIG_CM_NAMESPACE}/{cm_name}" on the target cluster.'
        ' Deploy the cluster quota chart first, drop --team to bypass'
        ' team-based routing, or set the ConfigMap name via'
        ' `xpk config set team-configmap-name <name>` if your cluster'
        ' uses a different name.'
    )
    xpk_exit(1)
  if args.team not in (cfg.get('teams') or {}):
    teams = available_teams(cfg)
    hints = suggest(args.team, teams)
    hint_line = f' Did you mean: {", ".join(hints)}?' if hints else ''
    xpk_print(
        f'ERROR: --team={args.team!r} not found on this cluster.{hint_line}'
        f' Available teams: {", ".join(teams) or "<none>"}'
    )
    xpk_exit(1)
  # The --declared-duration-minutes help text states it's required when
  # --team is set (the cluster-side time-limit controller relies on the
  # label to stop overrunning jobs). Enforce it here so the workload
  # doesn't silently submit without the duration label.
  if getattr(args, 'declared_duration_minutes', None) is None:
    xpk_print(
        'ERROR: --declared-duration-minutes is required when --team is set.'
    )
    xpk_exit(1)
  if getattr(args, 'value_class', None):
    vcs = available_value_classes(cfg)
    if vcs and args.value_class not in vcs:
      hints = suggest(args.value_class, vcs)
      hint_line = f' Did you mean: {", ".join(hints)}?' if hints else ''
      xpk_print(
          f'ERROR: --value-class={args.value_class!r} not valid on this'
          f' cluster.{hint_line} Available: {", ".join(vcs)}'
      )
      xpk_exit(1)
  args.quota_cfg = cfg
  return cfg


def resolve_team_for_args(args) -> TeamRouting | None:
  """Return TeamRouting when --team was set, or None when it was not.

  Callers decide what to do with None — `workload create` falls back to
  upstream LocalQueue + args.priority; `workload status` errors out
  because --team is required there.
  """
  cfg = load_quota_cfg(args)
  if cfg is None:
    return None
  return resolve_team(cfg, args.team)


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
