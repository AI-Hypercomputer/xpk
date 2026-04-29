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

"""`xpk workload status` — focused, plain-English diagnosis for a single workload.

Differs from `xpk inspector` (which dumps cluster-wide raw state for SREs):
this command answers "why is *my* job stuck?" with a 3-line answer plus a
specific fix when an AdmissionCheck error or queue position can be diagnosed.
Reads the team-quota ConfigMap to resolve the team's namespace + ClusterQueue.
"""

import json as _json
import subprocess as _subprocess
from datetime import datetime, timezone

from ..core.cluster import get_cluster_credentials
from ..core.commands import run_command_for_value
from ..utils.console import xpk_exit, xpk_print
from ..utils.validation import (
    SystemDependency,
    should_validate_dependencies,
    validate_dependencies_list,
)


def workload_status(args) -> None:
  """Show team-Kueue queue status for a workload or an entire team namespace.

  Tells the user if their workload is running, queued normally, or stuck,
  and provides a plain-English diagnosis with fix instructions.

  Args:
    args: user provided arguments (--cluster, --team, --workload).
  """
  if should_validate_dependencies(args):
    validate_dependencies_list(
        args, [SystemDependency.KUBECTL, SystemDependency.GCLOUD]
    )

  # Fill project from gcloud config if not provided.
  if not getattr(args, 'project', None):
    r = _subprocess.run(
        ['gcloud', 'config', 'get', 'project'],
        capture_output=True,
        text=True,
        check=False,
    )
    args.project = (
        r.stdout.strip().splitlines()[-1] if r.returncode == 0 else ''
    )
  if not args.project:
    xpk_print(
        'ERROR: --project not set and could not be determined from gcloud'
        ' config.'
    )
    xpk_exit(1)

  # Look up the cluster location directly — avoids requiring compute/zone in
  # gcloud config (which get_cluster_credentials needs but users often lack).
  if not getattr(args, 'zone', None):
    rc, loc = run_command_for_value(
        f'gcloud container clusters list --project={args.project}'
        f' --filter=name={args.cluster} --format="value(location)"',
        task='Find cluster location',
        quiet=True,
    )
    if rc != 0 or not loc.strip():
      xpk_print(
          f'ERROR: Could not find cluster "{args.cluster}" in project'
          f' {args.project}.'
      )
      xpk_exit(1)
    args.zone = loc.strip()

  get_cluster_credentials(args)

  # Imported lazily to avoid a circular import: commands/workload.py imports
  # this module's parser, and we'd otherwise close the loop.
  from .workload import _resolve_quota_team  # pylint: disable=import-outside-toplevel

  routing = _resolve_quota_team(args)
  namespace = routing.namespace
  cq_name = namespace  # ClusterQueue name matches namespace name

  def _kube_json(*kubectl_args):
    cmd = 'kubectl ' + ' '.join(kubectl_args) + ' -o json'
    rc, out = run_command_for_value(cmd, task=cmd, quiet=True)
    if rc != 0 or not out:
      return None
    try:
      return _json.loads(out)
    except _json.JSONDecodeError:
      return None

  def _events_text(ns, name):
    cmd = (
        f'kubectl get events -n {ns}'
        f' --field-selector involvedObject.name={name}'
        ' --sort-by=.lastTimestamp'
    )
    rc, out = run_command_for_value(cmd, task='get events', quiet=True)
    return out.strip() if rc == 0 else ''

  def _age(ts_str):
    if not ts_str:
      return '?'
    ts = datetime.fromisoformat(ts_str.replace('Z', '+00:00'))
    s = int((datetime.now(timezone.utc) - ts).total_seconds())
    if s < 60:
      return f'{s}s'
    if s < 3600:
      return f'{s // 60}m'
    return f'{s // 3600}h{(s % 3600) // 60}m'

  def _cond(wl, ctype):
    for c in wl.get('status', {}).get('conditions', []):
      if c.get('type') == ctype:
        return c
    return None

  def _is_true(c):
    return c is not None and c.get('status') == 'True'

  def _cq_chips(cq, section):
    total = 0
    for flavor in cq.get('status', {}).get(section, []):
      for res in flavor.get('resources', []):
        if res.get('name') == 'google.com/tpu':
          total += int(res.get('total', 0))
    return total

  def _cq_quota(cq):
    nominal, borrow = 0, 0
    for rg in cq.get('spec', {}).get('resourceGroups', []):
      for flavor in rg.get('flavors', []):
        for res in flavor.get('resources', []):
          if res.get('name') == 'google.com/tpu':
            nominal += int(res.get('nominalQuota', 0))
            b = res.get('borrowingLimit')
            if b is not None:
              borrow += int(b)
    return nominal, borrow

  def _ordinal(n):
    return (
        f"{n}{['th','st','nd','rd','th'][min(n % 10, 4) if n % 100 not in (11,12,13) else 0]}"
    )

  def _xpk_name_of(wl):
    name = wl['metadata'].get('labels', {}).get('xpk.google.com/workload')
    if name:
      return name
    for ref in wl['metadata'].get('ownerReferences', []):
      if ref.get('kind') in ('JobSet', 'Job'):
        return ref.get('name', '')
    n = wl['metadata']['name']
    if n.startswith('jobset-'):
      n = n[len('jobset-') :]
    if len(n) > 6 and n[-6] == '-':
      n = n[:-6]
    return n

  def _print_cq_summary(cq):
    if not cq:
      return
    st = cq.get('status', {})
    nominal, borrow_limit = _cq_quota(cq)
    running_chips = _cq_chips(cq, 'flavorsUsage')
    reserved_chips = _cq_chips(cq, 'flavorsReservation')
    admitted = st.get('admittedWorkloads', 0)
    reserving = st.get('reservingWorkloads', 0)
    pending = st.get('pendingWorkloads', 0)
    xpk_print(
        f'  Quota   : {nominal} chips nominal  +{borrow_limit} borrow  ='
        f' {nominal + borrow_limit} max'
    )
    if reserved_chips > 0 and reserved_chips != running_chips:
      xpk_print(
          f'  Reserved: {reserved_chips} chips'
          f' ({reserving} workload(s) — quota held, awaiting admission)'
      )
    xpk_print(
        f'  Running : {running_chips} chips ({admitted} workload(s) admitted)'
    )
    xpk_print(f'  Queued  : {pending} workload(s) waiting for quota')

  def _diagnose_one(wl, all_items, cq):
    kueue_name = wl['metadata']['name']
    xpk_name = _xpk_name_of(wl)
    created_at = wl['metadata']['creationTimestamp']

    cond_reserved = _cond(wl, 'QuotaReserved')
    cond_admitted = _cond(wl, 'Admitted')
    cond_finished = _cond(wl, 'Finished')

    is_admitted = _is_true(cond_admitted)
    is_reserved = _is_true(cond_reserved)
    is_finished = _is_true(cond_finished)
    finish_reason = cond_finished.get('reason', '') if cond_finished else ''

    xpk_print(f'Workload : {xpk_name}  ->  {kueue_name}')
    xpk_print(f'Age      : {_age(created_at)}')

    if is_finished:
      status_word = 'success' if finish_reason == 'Succeeded' else finish_reason
      xpk_print(f'Status   : FINISHED ({status_word})')
      msg = (cond_finished or {}).get('message', '')
      if msg:
        xpk_print(f'           {msg}')
      xpk_print('')
      return

    if is_admitted:
      admitted_ts = (cond_admitted or {}).get('lastTransitionTime', '')
      xpk_print(f'Status   : RUNNING  (admitted {_age(admitted_ts)} ago)')
      xpk_print(f'Team quota ({cq_name}):')
      _print_cq_summary(cq)
      xpk_print('')
      return

    if is_reserved:
      reserved_ts = (cond_reserved or {}).get('lastTransitionTime', '')
      xpk_print(
          'Status   : STUCK — quota reserved but not admitted'
          f' ({_age(reserved_ts)} ago)'
      )
      xpk_print(f'Team quota ({cq_name}):')
      _print_cq_summary(cq)
      events = _events_text(namespace, kueue_name)
      warn = [
          l
          for l in events.splitlines()
          if any(
              w in l for w in ('Warning', 'Error', 'Failed', 'error', 'failed')
          )
      ]
      if warn:
        xpk_print('Diagnosis: AdmissionCheck failed. Error(s):')
        for line in warn[-3:]:
          xpk_print(f'  {line.strip()}')
        if 'more than 49 characters' in events:
          max_len = 23 - len(namespace)
          xpk_print('')
          xpk_print(
              f'  Fix: --workload name "{xpk_name}" ({len(xpk_name)} chars)'
              f' exceeds the {max_len}-char limit for {namespace}.'
          )
          xpk_print(
              '       Delete the JobSet and resubmit with a name <='
              f' {max_len} chars.'
          )
          xpk_print(f'       Example: {xpk_name[:max_len]}')
      else:
        xpk_print('Diagnosis: AdmissionCheck still processing (no errors yet).')
        xpk_print(f'  kubectl describe workload {kueue_name} -n {namespace}')
      xpk_print('')
      return

    # Queued — compute position
    my_ts = created_at
    my_pri = wl.get('spec', {}).get('priority') or 0
    ahead = []
    for other in all_items:
      oname = other['metadata']['name']
      if oname == kueue_name:
        continue
      if _is_true(_cond(other, 'Admitted')) or _is_true(
          _cond(other, 'Finished')
      ):
        continue
      if _is_true(_cond(other, 'QuotaReserved')):
        continue
      other_ts = other['metadata']['creationTimestamp']
      other_pri = other.get('spec', {}).get('priority') or 0
      if other_pri > my_pri or (other_pri == my_pri and other_ts < my_ts):
        ahead.append(_xpk_name_of(other))

    pos = len(ahead) + 1
    xpk_print('Status   : QUEUED — waiting for quota')
    if ahead:
      sample = ', '.join(ahead[:3]) + ('...' if len(ahead) > 3 else '')
      xpk_print(
          f'Position : {_ordinal(pos)} in line  ({len(ahead)} workload(s)'
          f' ahead: {sample})'
      )
    else:
      xpk_print(
          f'Position : {_ordinal(pos)} in line  (nothing ahead of you in this'
          ' queue)'
      )
    xpk_print(f'Team quota ({cq_name}):')
    _print_cq_summary(cq)

    # Anomaly detection
    st = (cq or {}).get('status', {})
    nominal, _ = _cq_quota(cq) if cq else (0, 0)
    running = _cq_chips(cq, 'flavorsUsage') if cq else 0
    if (
        pos == 1
        and st.get('admittedWorkloads', 0) == 0
        and running == 0
        and nominal > 0
    ):
      xpk_print(
          "Diagnosis: You're 1st in line with quota available but nothing"
          ' running.'
      )
      xpk_print(
          f'  This is unusual. Check: kubectl describe workload {kueue_name} -n'
          f' {namespace}'
      )
    elif pos == 1 and nominal > 0 and running < nominal * 0.9:
      xpk_print(
          "Diagnosis: You're 1st in line and quota is not full — should be"
          ' admitted soon.'
      )
      xpk_print('  If still queued in a few minutes, check:')
      xpk_print(f'  kubectl describe workload {kueue_name} -n {namespace}')
    else:
      xpk_print(
          'Diagnosis: Things look normal — waiting behind other workloads.'
      )
    xpk_print('')

  cq = _kube_json('get', 'clusterqueue', cq_name)
  all_wl_data = _kube_json('get', 'workload', '-n', namespace)
  all_items = all_wl_data.get('items', []) if all_wl_data else []

  if args.workload:
    prefix = f'jobset-{args.workload}-'
    matches = [i for i in all_items if i['metadata']['name'].startswith(prefix)]
    if not matches:
      xpk_print(f'No workload found matching "{prefix}*" in {namespace}')
      xpk_exit(1)
    if len(matches) > 1:
      names = [i['metadata']['name'] for i in matches]
      xpk_print(
          f'Multiple matches: {names}. Use the full Kueue name with --workload.'
      )
      xpk_exit(1)
    _diagnose_one(matches[0], all_items, cq)
  else:
    if not all_items:
      xpk_print(f'No workloads in {namespace} — queue is empty.')
      xpk_print(f'Team quota ({cq_name}):')
      if cq:
        nominal, borrow = _cq_quota(cq)
        xpk_print(
            f'  Quota: {nominal} chips nominal  +{borrow} borrow  ='
            f' {nominal + borrow} max'
        )
      xpk_exit(0)

    def _sort_key(i):
      return (
          0 if _is_true(_cond(i, 'Admitted')) else 1,
          i['metadata']['creationTimestamp'],
      )

    for item in sorted(all_items, key=_sort_key):
      _diagnose_one(item, all_items, cq)

  xpk_exit(0)
