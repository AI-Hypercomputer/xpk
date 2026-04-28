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

"""Tiny per-cluster cache of PoC config for faster errors + tab completion.

Populated automatically whenever xpk successfully fetches the `poc-team-config`
ConfigMap from a cluster. Read by:
  - argcomplete completers (sub-second tab completion without a cluster call)
  - error-message suggesters ("did you mean ...")

No secrets are stored. The cache is advisory: if it is stale, out of sync, or
absent, xpk falls through to live discovery with no behavior change.

Layout:
  ~/.xpk/poc-cache/<kubectl-context>.json
"""

import datetime as _dt
import json
import os
import subprocess
import tempfile
from pathlib import Path

CACHE_DIR = Path.home() / ".xpk" / "poc-cache"
DEFAULT_TTL = _dt.timedelta(hours=1)


def _safe_key(name: str) -> str:
  return "".join(c if c.isalnum() or c in "-._" else "_" for c in name)


def _path_for(context: str) -> Path:
  return CACHE_DIR / f"{_safe_key(context)}.json"


def current_context() -> str | None:
  """Return the current kubectl context, or None."""
  try:
    r = subprocess.run(
        ["kubectl", "config", "current-context"],
        capture_output=True, text=True, timeout=5,
    )
  except (FileNotFoundError, subprocess.TimeoutExpired):
    return None
  if r.returncode != 0:
    return None
  return (r.stdout or "").strip() or None


def write(context: str, cfg: dict) -> None:
  """Persist cfg under this cluster's context. Best-effort."""
  if not context:
    return
  try:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    try:
      os.chmod(CACHE_DIR, 0o700)
    except OSError:
      pass
    payload = {
        "context":      context,
        "fetchedAt":    _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
        "teams":        sorted((cfg.get("teams") or {}).keys()),
        "valueClasses": list(cfg.get("valueClasses") or []),
        "sliceName":    cfg.get("sliceName") or {},
    }
    dst = _path_for(context)
    with tempfile.NamedTemporaryFile(
        "w", dir=CACHE_DIR, delete=False, encoding="utf-8"
    ) as tmp:
      json.dump(payload, tmp, indent=2)
      tmp.flush()
      os.fsync(tmp.fileno())
      tmp_path = Path(tmp.name)
    os.chmod(tmp_path, 0o600)
    tmp_path.replace(dst)
  except Exception:  # pylint: disable=broad-except
    pass  # cache is strictly best-effort


def read(context: str) -> dict | None:
  """Return cached payload for this context, or None."""
  if not context:
    return None
  try:
    p = _path_for(context)
    if not p.exists():
      return None
    return json.loads(p.read_text())
  except Exception:  # pylint: disable=broad-except
    return None


def invalidate(context: str) -> None:
  try:
    _path_for(context).unlink(missing_ok=True)
  except Exception:  # pylint: disable=broad-except
    pass


def is_fresh(payload: dict, ttl: _dt.timedelta = DEFAULT_TTL) -> bool:
  try:
    ts = _dt.datetime.fromisoformat(payload["fetchedAt"])
  except (KeyError, ValueError):
    return False
  if ts.tzinfo is None:
    ts = ts.replace(tzinfo=_dt.timezone.utc)
  return _dt.datetime.now(_dt.timezone.utc) - ts <= ttl


def all_contexts() -> list[str]:
  """Every cluster context we've cached — used by completers when the user
  hasn't yet specified --cluster."""
  if not CACHE_DIR.exists():
    return []
  out = []
  for p in CACHE_DIR.glob("*.json"):
    try:
      c = json.loads(p.read_text()).get("context")
      if c:
        out.append(c)
    except Exception:  # pylint: disable=broad-except
      continue
  return out


def gke_contexts_from_kubeconfig() -> list[str]:
  """Return kubectl contexts that look like GKE clusters (prefix gke_).
  Used to tab-complete the --cluster flag."""
  try:
    r = subprocess.run(
        ["kubectl", "config", "get-contexts", "-o", "name"],
        capture_output=True, text=True, timeout=5,
    )
  except (FileNotFoundError, subprocess.TimeoutExpired):
    return []
  if r.returncode != 0:
    return []
  ctxs = [line.strip() for line in r.stdout.splitlines() if line.strip()]
  # xpk uses the short cluster name, not the full context — strip the GKE prefix
  # pattern: gke_<project>_<location>_<cluster>
  names = set()
  for c in ctxs:
    if c.startswith("gke_"):
      parts = c.split("_", 3)
      if len(parts) == 4:
        names.add(parts[3])
    else:
      names.add(c)
  return sorted(names)
