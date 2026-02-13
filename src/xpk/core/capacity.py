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

import enum
import json
import functools
from dataclasses import dataclass, field
from typing import Any

from .commands import run_command_with_updates, run_command_for_value
from .system_characteristics import AcceleratorType
from ..utils.console import xpk_print, xpk_exit
from ..utils.kueue import is_queued_cluster

AUTOPROVISIONING_CONFIG_VALUE = 'AUTOPROVISION'
AUTOPROVISIONING_CONFIG_MINIMUM_KEY = 'minimum_chips'
AUTOPROVISIONING_CONFIG_MAXIMUM_KEY = 'maximum_chips'
CAPACITY_TYPE_CONFIG_KEY = 'capacity_type'

H100_DEVICE_TYPE = 'h100-80gb-8'
H100_MEGA_DEVICE_TYPE = 'h100-mega-80gb-8'
H200_DEVICE_TYPE = 'h200-141gb-8'
B200_DEVICE_TYPE = 'b200-8'
GB200_DEVICE_TYPE = 'gb200-4'
GB200_DEVICE_TYPE_NOLSSD = 'gb200-4-no-ssd'
RESERVATION_CONFIG_KEY = 'reservation_id'


class CapacityType(enum.Enum):
  ON_DEMAND = 'on_demand'
  RESERVATION = 'reservation'
  SPOT = 'spot'
  UNKNOWN = 'unknown'
  FLEX_START = 'flex_start'


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
  acceleratorCount: int
  acceleratorType: str


@dataclass(frozen=True)
class _SpecificReservation:
  count: int
  inUseCount: int
  machine_type: str
  guest_accelerators: list[_AcceleratorResource] = field(default_factory=list)
  maintenance_interval: str = ''


@dataclass(frozen=True)
class _AggregateReservation:
  reservedResources: list[_AcceleratorResource]
  inUseResources: list[_AcceleratorResource]


@dataclass(frozen=True)
class _Reservation:
  name: str
  specificReservation: _SpecificReservation | None
  aggregateReservation: _AggregateReservation | None
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
      inUseCount=int(data.get('inUseCount', 0)),
      machine_type=machine_type,
      guest_accelerators=guest_accelerators,
      maintenance_interval=maintenance_interval,
  )


def _parse_accelerator_resource(data: dict[str, Any]) -> _AcceleratorResource:
  return _AcceleratorResource(
      acceleratorCount=int(data.get('acceleratorCount', 0)),
      acceleratorType=str(data.get('acceleratorType', '')),
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
      reservedResources=reserved_resources, inUseResources=in_use_resources
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
      specificReservation=specific_reservation,
      aggregateReservation=aggregate_reservation,
      deployment_type=deployment_type,
      resource_policy=resource_policy,
  )


@functools.lru_cache(maxsize=None)
def _fetch_reservation_from_gcloud(
    project: str, zone: str, name: str
) -> _Reservation | None:
  """Fetches reservation details using gcloud and returns _Reservation object.

  Args:
    project: Project ID.
    zone: Zone.
    name: Reservation name.

  Returns:
    _Reservation object or None on failure.
  """
  command = (
      f'gcloud beta compute reservations describe {name} '
      f'--project={project} --zone={zone} '
      '--format="json(specificReservation,aggregateReservation,status,deploymentType,resourcePolicies)"'
  )
  # Basic dry run value to avoid crashes if dry run is enabled globally
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
      f'Get reservation {name}',
      dry_run_return_val=dry_run_json,
  )

  if return_code != 0 or not output.strip():
    return None

  try:
    data = json.loads(output)
    if not data or data.get('status') != 'READY':
      return None
    return _parse_reservation(name, data)
  except (ValueError, IndexError, AttributeError, json.JSONDecodeError) as e:
    xpk_print(f'Error processing reservation data: {e}. Output: "{output}".')
    return None


def _get_reservation_cached(
    reservation: ReservationLink,
) -> _Reservation | None:
  """Fetches reservation details using gcloud and returns _Reservation object.

  Args:
    reservation: ReservationLink object.

  Returns:
    _Reservation object or None on failure.
  """
  return _fetch_reservation_from_gcloud(
      project=reservation.project, zone=reservation.zone, name=reservation.name
  )


_get_reservation_cached.cache_clear = _fetch_reservation_from_gcloud.cache_clear  # type: ignore


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


def get_capacity_type(args) -> tuple[CapacityType, int]:
  """Determine the capacity type based on user arguments.

  Args:
    args: user provided arguments for running the command.

  Returns:
    Tuple with string with the system characteristics and
    int of 0 if successful and 1 otherwise.
  """
  capacity_type = CapacityType.UNKNOWN
  num_types = 0
  return_code = 0

  # Determine the capacity argument.
  if args.on_demand:
    capacity_type = CapacityType.ON_DEMAND
    num_types += 1
  if args.reservation:
    return_code = verify_reservations_exist(args)
    if return_code > 0:
      return capacity_type, return_code
    capacity_type = CapacityType.RESERVATION
    num_types += 1
  if args.spot:
    capacity_type = CapacityType.SPOT
    num_types += 1
  if args.flex:
    capacity_type = CapacityType.FLEX_START
    num_types += 1

  # Check that the number of user arguments provided is valid.
  if num_types == 0:
    capacity_type = CapacityType.UNKNOWN
  elif num_types != 1:
    xpk_print(
        'ERROR: User specified more than one of the following arguments. Please'
        ' specify only one of `--reservation=$RESERVATION_NAME`, `--on-demand`,'
        ' `--flex` or `--spot`.'
    )
    return_code = 1

  return capacity_type, return_code


def get_reservation_maintenance_interval(
    reservation: ReservationLink,
) -> str:
  """Get reservation maintenance interval.

  Args:
    reservation: reservation object.

  Returns:
    Maintenance interval as a string.
  """
  reservation_obj = _get_reservation_cached(reservation)
  if not reservation_obj or not reservation_obj.specificReservation:
    xpk_print(
        f'Get reservation maintenance interval failed for {reservation.name}'
    )
    xpk_exit(1)

  return reservation_obj.specificReservation.maintenance_interval


def get_reservation_placement_policy(reservation: ReservationLink) -> str:
  """Get reservation placement policy.

  Args:
    reservation: reservation object.

  Returns:
    Placement policy as a string.
  """
  reservation_obj = _get_reservation_cached(reservation)
  if not reservation_obj:
    xpk_print(f'Get reservation placement policy failed for {reservation.name}')
    xpk_exit(1)

  return reservation_obj.resource_policy


def get_reservation_deployment_type(reservation: ReservationLink) -> str:
  """Get reservation deployment type.

  Args:
    reservation: reservation object.

  Returns:
    Deployment type as a string.
  """
  reservation_obj = _get_reservation_cached(reservation)
  if not reservation_obj:
    xpk_print(f'Get reservation deployment type failed for {reservation.name}')
    xpk_exit(1)

  return reservation_obj.deployment_type


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


def get_capacity_arguments_from_capacity_type(
    args,
    capacity_type: CapacityType,
    max_nodes: int,
    accelerator_type: AcceleratorType,
    reservation_name: str | None,
) -> tuple[str, int]:
  """Determine the Nodepool creation capacity arguments needed.

  Args:
    args: user provided arguments for running the command.
    capacity_type: The type of capacity the user configured.

  Returns:
    Tuple with string with the capacity argument to use and
    int of 0 if successful and 1 otherwise.
  """
  capacity_args = ''
  return_code = 0

  match capacity_type:
    case CapacityType.ON_DEMAND:
      capacity_args = ''
    case CapacityType.SPOT:
      capacity_args = '--spot'
    case CapacityType.FLEX_START:
      capacity_args = (
          ' --flex-start --enable-autoscaling'
          ' --location-policy=ANY --reservation-affinity=none'
          f' --no-enable-autorepair --max-nodes={max_nodes}'
      )
      if is_queued_cluster(args.num_slices, accelerator_type):
        capacity_args += ' --enable-queued-provisioning'
    case CapacityType.RESERVATION:
      capacity_args = (
          f'--reservation-affinity=specific --reservation={reservation_name}'
      )
    case _:
      xpk_print(
          f'Unknown capacity type: {capacity_type}. Unable to determine'
          ' capacity args.'
      )
      return_code = 1
  return capacity_args, return_code


def get_capacity_node_selectors_from_capacity_type(
    capacity_type: str,
    reservation: ReservationLink | None,
    cluster_project: str,
) -> tuple[str, int]:
  """Determine the node selectors for a workload to run on a specific capacity type.

  Args:
    capacity_type: The type of capacity the user configured.
    reservation: The reservation to use. Set to None if not
      using reservations.
    cluster_project: The project of the cluster.

  Returns:
    Tuple with string with the node selectors to use and
    int of 0 if successful and 1 otherwise.
  """
  node_selector = ''
  return_code = 0

  match capacity_type:
    case CapacityType.ON_DEMAND.name:
      node_selector = ''
    case CapacityType.FLEX_START.name:
      node_selector = 'cloud.google.com/gke-queued: "true"'
    case CapacityType.SPOT.name:
      node_selector = 'cloud.google.com/gke-spot: "true"'
    case CapacityType.RESERVATION.name:
      assert reservation is not None
      reservation_name = to_reservation_path(reservation, cluster_project)
      node_selector = f'cloud.google.com/reservation-name: {reservation_name}'
    case _:
      xpk_print(
          f'Unknown capacity type: {capacity_type}. Unable to determine the'
          ' node selectors.'
      )
      return_code = 1
  return node_selector, return_code


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
