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

import json
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

from .commands import run_command_with_updates, run_command_for_value
from ..utils.console import xpk_print, xpk_exit

RESERVATION_CONFIG_KEY = 'reservation_id'


@dataclass(frozen=True)
class ReservationLink:
  project: str
  name: str
  zone: str


@dataclass(frozen=True)
class BlockReservationLink(ReservationLink):
  block_name: str


@dataclass(frozen=True)
class SubBlockReservationLink(BlockReservationLink):
  sub_block_name: str


@dataclass(frozen=True)
class _AcceleratorResource:
  accelerator_count: int
  accelerator_type: str


@dataclass(frozen=True)
class _SpecificReservation:
  count: int
  in_use_count: int
  machine_type: str
  guest_accelerators: list[_AcceleratorResource] = field(default_factory=list)
  maintenance_interval: str = ''


@dataclass(frozen=True)
class _AggregateReservation:
  reserved_resources: list[_AcceleratorResource]
  in_use_resources: list[_AcceleratorResource]


@dataclass(frozen=True)
class _Reservation:
  name: str
  specific_reservation: _SpecificReservation | None
  aggregate_reservation: _AggregateReservation | None
  deployment_type: str = ''
  resource_policy: str = ''


def _parse_specific_reservation(data: dict[str, Any]) -> _SpecificReservation:
  instance_properties = data.get('instanceProperties', {})
  machine_type = instance_properties.get('machineType', '')
  guest_accelerators_data = instance_properties.get('guestAccelerators', [])
  guest_accelerators = [
      _parse_accelerator_resource(acc) for acc in guest_accelerators_data
  ]
  maintenance_interval = instance_properties.get('maintenanceInterval', '')

  return _SpecificReservation(
      count=int(data.get('count', 0)),
      in_use_count=int(data.get('inUseCount', 0)),
      machine_type=machine_type,
      guest_accelerators=guest_accelerators,
      maintenance_interval=maintenance_interval,
  )


def _parse_accelerator_resource(data: dict[str, Any]) -> _AcceleratorResource:
  return _AcceleratorResource(
      accelerator_count=int(data.get('acceleratorCount', 0)),
      accelerator_type=str(data.get('acceleratorType', '')),
  )


def _parse_aggregate_reservation(data: dict[str, Any]) -> _AggregateReservation:
  reserved_resources = [
      _parse_accelerator_resource(r['accelerator'])
      for r in data.get('reservedResources', [])
      if 'accelerator' in r
  ]
  in_use_resources = [
      _parse_accelerator_resource(r['accelerator'])
      for r in data.get('inUseResources', [])
      if 'accelerator' in r
  ]
  return _AggregateReservation(
      reserved_resources=reserved_resources, in_use_resources=in_use_resources
  )


def _parse_reservation(name: str, data: dict[str, Any]) -> _Reservation:
  specific_reservation = None
  if 'specificReservation' in data:
    specific_reservation = _parse_specific_reservation(
        data['specificReservation']
    )

  aggregate_reservation = None
  if 'aggregateReservation' in data:
    aggregate_reservation = _parse_aggregate_reservation(
        data['aggregateReservation']
    )

  deployment_type = data.get('deploymentType', '')
  resource_policy = data.get('resourcePolicies', {}).get('policy', '')

  return _Reservation(
      name=name,
      specific_reservation=specific_reservation,
      aggregate_reservation=aggregate_reservation,
      deployment_type=deployment_type,
      resource_policy=resource_policy,
  )


@lru_cache()
def _get_reservation_cached(
    reservation: ReservationLink,
) -> _Reservation | None:
  """Fetches reservation details using gcloud and returns _Reservation object.

  Args:
    reservation: ReservationLink object.

  Returns:
    _Reservation object or None on failure.
  """
  command = (
      f'gcloud beta compute reservations describe {reservation.name} '
      f'--project={reservation.project} --zone={reservation.zone} '
      '--format="json(specificReservation,aggregateReservation,status,deploymentType,resourcePolicies)"'
  )
  dry_run_json = json.dumps({
      'specificReservation': {
          'count': 100,
          'inUseCount': 0,
          'instanceProperties': {},
      },
      'status': 'READY',
      'deploymentType': 'DENSE',
  })

  return_code, output = run_command_for_value(
      command,
      f'Get reservation {reservation.name}',
      dry_run_return_val=dry_run_json,
  )

  if return_code != 0 or not output.strip():
    return None

  try:
    data = json.loads(output)
    if not data or data.get('status') != 'READY':
      return None
    return _parse_reservation(reservation.name, data)
  except (ValueError, IndexError, AttributeError, json.JSONDecodeError) as e:
    xpk_print(f'Error processing reservation data: {e}. Output: "{output}".')
    return None


def print_reservations(args) -> int:
  """Print the reservations in the project.

  Args:
    args: user provided arguments for running the command.

  Returns:
    0 if successful and 1 otherwise.
  """
  command = f'gcloud beta compute reservations list --project={args.project}'
  return_code = run_command_with_updates(
      command, 'Get all reservations in the project'
  )
  if return_code != 0:
    xpk_print(f'Get all reservations returned ERROR {return_code}')
    return 1
  return 0


def get_reservation_maintenance_interval(
    reservation_link: ReservationLink,
) -> str:
  """Get reservation maintenance interval.

  Args:
    reservation_link: reservation object.

  Returns:
    Maintenance interval as a string.
  """
  reservation = _get_reservation_cached(reservation_link)
  if not reservation or not reservation.specific_reservation:
    xpk_print(
        'Get reservation maintenance interval failed for'
        f' {reservation_link.name}'
    )
    xpk_exit(1)

  return reservation.specific_reservation.maintenance_interval


def get_reservation_placement_policy(reservation_link: ReservationLink) -> str:
  """Get reservation placement policy.

  Args:
    reservation_link: reservation object.

  Returns:
    Placement policy as a string.
  """
  reservation = _get_reservation_cached(reservation_link)
  if not reservation:
    xpk_print(
        f'Get reservation placement policy failed for {reservation_link.name}'
    )
    xpk_exit(1)

  return reservation.resource_policy


def get_reservation_deployment_type(reservation_link: ReservationLink) -> str:
  """Get reservation deployment type.

  Args:
    reservation_link: reservation object.

  Returns:
    Deployment type as a string.
  """
  reservation = _get_reservation_cached(reservation_link)
  if not reservation:
    xpk_print(
        f'Get reservation deployment type failed for {reservation_link.name}'
    )
    xpk_exit(1)

  return reservation.deployment_type


def get_reservations_list(args) -> list[ReservationLink]:
  """Get the list of reservations from args.

  Args:
    args: user provided arguments.

  Returns:
    List of ReservationLink objects.
  """
  if not args.reservation:
    return []
  return [
      parse_reservation(r.strip(), args.project, args.zone)
      for r in args.reservation.split(',')
  ]


def verify_reservations_exist(args) -> int:
  """Verify the reservations exist.

  Args:
    args: user provided arguments for running the command.

  Returns:
    0 if successful and 1 otherwise.
  """
  for reservation_link in get_reservations_list(args):
    reservation = _get_reservation_cached(reservation_link)
    if not reservation:
      xpk_print(f'Describe reservation {reservation_link.name} failed')
      xpk_print(
          'Please confirm that your reservation name'
          f' {reservation_link.name} is correct.'
      )
      return 1
  return 0


def parse_reservation(
    reservation_path: str, cluster_project: str, zone: str
) -> ReservationLink:
  """Parses the reservation details from the reservation path.

  Args:
    reservation_path: path in format `[projects/RESERVATION_PROJECT_ID/reservations/]RESERVATION_NAME[/reservationBlocks/BLOCK_NAME[/reservationSubBlocks/SUB_BLOCK_NAME]]`
    cluster_project: the default cluster project
    zone: the reservation zone

  Returns:
    ReservationLink instance containing reservation details.
  """
  reservation = _try_parse_reservation(reservation_path, cluster_project, zone)
  if reservation is None:
    xpk_print('Unable to parse reservation: ', reservation_path)
    xpk_exit(1)
  return reservation


def _try_parse_reservation(
    reservation_path: str, cluster_project: str, zone: str
) -> ReservationLink | None:
  parts = reservation_path.split('/')
  if not all(parts):
    return None

  project = cluster_project
  if parts[0] == 'projects':
    if len(parts) < 4 or parts[2] != 'reservations':
      return None
    project = parts[1]
    parts = parts[3:]  # remove projects/PROJECT/reservations/ prefix

  match len(parts):
    case 1:
      return ReservationLink(project=project, name=parts[0], zone=zone)
    case 3 if parts[1] == 'reservationBlocks':
      return BlockReservationLink(
          project=project, name=parts[0], zone=zone, block_name=parts[2]
      )
    case 5 if (
        parts[1] == 'reservationBlocks' and parts[3] == 'reservationSubBlocks'
    ):
      return SubBlockReservationLink(
          project=project,
          name=parts[0],
          zone=zone,
          block_name=parts[2],
          sub_block_name=parts[4],
      )
    case _:
      return None


def to_reservation_path(
    reservation: ReservationLink, cluster_project: str
) -> str:
  """Convert reservation to path string."""
  if reservation.project == cluster_project:
    path = reservation.name
  else:
    path = f'projects/{reservation.project}/reservations/{reservation.name}'

  if isinstance(reservation, BlockReservationLink):
    path += f'/reservationBlocks/{reservation.block_name}'
    if isinstance(reservation, SubBlockReservationLink):
      path += f'/reservationSubBlocks/{reservation.sub_block_name}'
  return path
