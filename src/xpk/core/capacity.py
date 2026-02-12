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
import os
import json
import functools
from dataclasses import dataclass, field
from typing import Sequence, Any

from .commands import run_command_with_updates, run_command_for_value
from .system_characteristics import AcceleratorType, SystemCharacteristics
from .gcloud_context import project_id_to_project_number
from ..utils.console import xpk_print, xpk_exit
from ..utils.kueue import is_queued_cluster
from ..utils.execution_context import is_dry_run

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
class ReservationCapacity:
  reservation: ReservationLink
  available_slices: int


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


@dataclass(frozen=True)
class _AggregateReservation:
  reservedResources: list[_AcceleratorResource]
  inUseResources: list[_AcceleratorResource]


@dataclass(frozen=True)
class _ReservationSubBlock:
  name: str
  count: int
  in_use_count: int


@dataclass(frozen=True)
class _Reservation:
  name: str
  specificReservation: _SpecificReservation | None
  aggregateReservation: _AggregateReservation | None


def _parse_specific_reservation(data: dict[str, Any]) -> _SpecificReservation:
  instance_properties = data.get('instanceProperties', {})
  machine_type = instance_properties.get('machineType', '')
  guest_accelerators_data = instance_properties.get('guestAccelerators', [])
  guest_accelerators = [
      _parse_accelerator_resource(acc) for acc in guest_accelerators_data
  ]

  return _SpecificReservation(
      count=int(data.get('count', 0)),
      inUseCount=int(data.get('inUseCount', 0)),
      machine_type=machine_type,
      guest_accelerators=guest_accelerators,
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

  return _Reservation(
      name=name,
      specificReservation=specific_reservation,
      aggregateReservation=aggregate_reservation,
  )


def _parse_reservation_sub_block(data: dict[str, Any]) -> _ReservationSubBlock:
  return _ReservationSubBlock(
      name=str(data.get('name', '')),
      count=int(data.get('count', 0)),
      in_use_count=int(data.get('inUseCount', '0')),
  )


@functools.lru_cache(maxsize=None)
def _get_reservation_cached(
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
      '--format="json(specificReservation,aggregateReservation,status)"'
  )
  # Basic dry run value to avoid crashes if dry run is enabled globally
  dry_run_json = json.dumps({
      'specificReservation': {
          'count': 100,
          'inUseCount': 0,
          'instanceProperties': {},
      },
      'status': 'READY',
  })

  return_code, output = run_command_for_value(
      command, f'Get reservation {name}', dry_run_return_val=dry_run_json
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


def get_reservation_maintenance_interval(reservation: ReservationLink) -> str:
  """Get reservation maintenance interval.

  Args:
    reservation: reservation object.

  Returns:
    Maintenance interval as a string.
  """
  command = (
      f'gcloud beta compute reservations describe {reservation.name}'
      f' --project={reservation.project} --zone={reservation.zone} --format="value(specificReservation.instanceProperties.maintenanceInterval)"'
  )
  return_code, output = run_command_for_value(
      command, 'Get reservation maintenance interval'
  )
  if return_code != 0:
    xpk_print(f'Get reservation maintenance interval ERROR {return_code}')
    xpk_exit(1)
  return output.strip()


def get_reservation_placement_policy(reservation: ReservationLink) -> str:
  """Get reservation placement policy.

  Args:
    reservation: reservation object.

  Returns:
    Placement policy as a string.
  """
  command = (
      f'gcloud beta compute reservations describe {reservation.name}'
      f' --project={reservation.project} --zone={reservation.zone} --format="value(resourcePolicies.policy)"'
  )
  return_code, output = run_command_for_value(
      command, 'Get reservation placement policy'
  )
  if return_code != 0:
    xpk_print(f'Get reservation placement policy ERROR {return_code}')
    xpk_exit(1)
  return output.strip()


def get_reservation_deployment_type(reservation: ReservationLink) -> str:
  """Get reservation deployment type.

  Args:
    reservation: reservation object.

  Returns:
    Deployment type as a string.
  """
  command = (
      f'gcloud beta compute reservations describe {reservation.name}'
      f' --project={reservation.project} --zone={reservation.zone} --format="value(deploymentType)"'
  )
  return_code, output = run_command_for_value(
      command, 'Get reservation deployment type', dry_run_return_val='DENSE'
  )
  if return_code != 0:
    xpk_print(f'Get reservation deployment type ERROR {return_code}')
    xpk_exit(1)
  return output.strip()


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
  for reservation in get_reservations_list(args):
    command = (
        f'gcloud beta compute reservations describe {reservation.name}'
        f' --project={reservation.project} --zone={reservation.zone}'
    )
    return_code = run_command_with_updates(
        command, 'Describe reservation', verbose=False
    )
    if return_code != 0:
      xpk_print(f'Describe reservation returned ERROR {return_code}')
      xpk_print(
          f'Please confirm that your reservation name {reservation.name} is'
          ' correct.'
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


def assess_available_slices(
    reservations: Sequence[ReservationLink],
    force_sub_block_targeting: bool,
    required_hosts: int,
    system: SystemCharacteristics,
) -> tuple[list[ReservationCapacity], int]:
  """Assess the available slices in the reservations.

  Args:
    reservations: list of reservations to assess.
    force_sub_block_targeting: if `True`, then the passed `ReservationLink` or `BlockReservationLink` will be flattened to adequate sub-blocks.
    required_hosts: number of hosts required per slice.
    system: The system characteristics of the accelerator type.

  Returns:
    List of capacity reservations with available slices.
  """
  reservation_capacities = []
  for reservation in reservations:
    capacities, return_code = _assess_available_slices_for_reservation(
        reservation, force_sub_block_targeting, required_hosts, system
    )
    if return_code != 0:
      return [], 0
    reservation_capacities.extend(capacities)

  # Deduplicate reservation_capacities, preserving order:
  reservation_capacities = list(dict.fromkeys(reservation_capacities))

  return reservation_capacities, 0


def _get_dry_run_sub_blocks() -> str:
  """Get dry run sub-blocks based on environment variable."""
  default_json = '[{"name": "sub0", "count": 16, "inUseCount": 0}]'
  return os.getenv('DRY_RUN_RESERVATION_SUB_BLOCKS', default_json)


def _assess_available_slices_for_reservation(
    reservation: ReservationLink,
    force_sub_block_targeting: bool,
    required_hosts: int,
    system: SystemCharacteristics,
) -> tuple[list[ReservationCapacity], int]:
  """Assess the available slices for a single reservation.

  Args:
    reservation: reservation to assess.
    force_sub_block_targeting: if `True`, then the passed `ReservationLink` or `BlockReservationLink` will be flattened to adequate sub-blocks.
    required_hosts: number of hosts required per slice.
    system: The system characteristics of the accelerator type.

  Returns:
    List of available reservations (targeting sub-blocks if applicable).
  """
  # Identify the parent reservation (project, zone, name)
  parent_reservation = _get_reservation_cached(
      project=reservation.project,
      zone=reservation.zone,
      name=reservation.name,
  )

  if not parent_reservation:
    xpk_print(f"WARNING: Failed to fetch reservation '{reservation.name}'.")
    return [], 0

  if not _verify_reservation_configuration(parent_reservation, system):
    return [], 0

  if isinstance(reservation, SubBlockReservationLink):
    available_slices, return_code = _get_available_slices_in_sub_block(
        reservation, required_hosts
    )
    if return_code != 0:
      return [], 0
    if available_slices > 0:
      return [ReservationCapacity(reservation, available_slices)], 0
    else:
      xpk_print(
          f'WARNING: Sub-block {reservation.sub_block_name} is either'
          ' unhealthy or not fitting. Skipping.'
      )
      return [], 0

  if force_sub_block_targeting:
    if isinstance(reservation, BlockReservationLink):
      return _get_healthy_and_fitting_sub_blocks_in_block(
          reservation, required_hosts
      )

    # reservation instanceof ReservationLink (not Block/SubBlock):
    blocks, return_code = _get_blocks_in_reservation(reservation)
    if return_code != 0:
      return [], 0
    if blocks:
      return assess_available_slices(
          blocks, force_sub_block_targeting, required_hosts, system
      )

    xpk_print(
        'WARNING: Super-slicing is enabled, but no blocks found in'
        f' reservation {reservation.name}. Skipping.'
    )
    return [], 0

  count, return_code = _get_reservation_count(
      parent_reservation, required_hosts, system, reservation
  )
  if return_code != 0:
    return [], return_code
  return ([ReservationCapacity(reservation, count)] if count > 0 else []), 0


def _list_healthy_sub_blocks(
    reservation: BlockReservationLink | SubBlockReservationLink,
) -> tuple[list[_ReservationSubBlock], int]:
  """List healthy sub-blocks for a reservation block or sub-block.

  Args:
    reservation: The reservation link (must be Block or SubBlock).

  Returns:
    A tuple containing a list of healthy sub-blocks and the return code.
  """
  filter_arg = 'healthInfo.healthStatus=HEALTHY'
  task_name = f'Count healthy fitting sub-blocks in {reservation.block_name}'
  dry_run_return_val = _get_dry_run_sub_blocks()

  if isinstance(reservation, SubBlockReservationLink):
    filter_arg = f'name={reservation.sub_block_name} AND {filter_arg}'
    task_name = f'Check sub-block {reservation.sub_block_name} health'
    dry_run_return_val = '[{"name": "sub0", "count": 16, "inUseCount": 0}]'

  command = (
      f'gcloud beta compute reservations sub-blocks list {reservation.name} '
      f'--block-name={reservation.block_name} '
      f'--project={reservation.project} '
      f'--zone={reservation.zone} '
      f'--filter="{filter_arg}" '
      '--format="json(name,count,inUseCount)"'
  )

  return_code, output = run_command_for_value(
      command,
      task_name,
      dry_run_return_val=dry_run_return_val,
  )

  if return_code != 0 or not output.strip():
    return [], return_code

  try:
    data = json.loads(output)
    if not data:
      return [], 0
    return [_parse_reservation_sub_block(row) for row in data], 0
  except (ValueError, IndexError, AttributeError, json.JSONDecodeError) as e:
    xpk_print(f'Error processing sub-block data: {e}. Output: "{output}".')
    return [], 1


def _get_available_slices_in_sub_block(
    reservation: SubBlockReservationLink,
    required_hosts: int,
) -> tuple[int, int]:
  """Check if a sub-block is healthy and return available slices."""
  sub_blocks, return_code = _list_healthy_sub_blocks(reservation)

  if return_code != 0 or not sub_blocks:
    return 0, return_code

  assert len(sub_blocks) == 1
  sub_block = sub_blocks[0]
  available_slices = (
      sub_block.count - sub_block.in_use_count
  ) // required_hosts
  return available_slices, 0


def _get_healthy_and_fitting_sub_blocks_in_block(
    reservation: BlockReservationLink,
    required_hosts: int,
) -> tuple[list[ReservationCapacity], int]:
  """Get healthy and fitting sub-blocks in a block."""
  sub_blocks, return_code = _list_healthy_sub_blocks(reservation)

  if return_code != 0:
    return [], return_code

  available_capacities: list[ReservationCapacity] = [
      ReservationCapacity(
          SubBlockReservationLink(
              project=reservation.project,
              name=reservation.name,
              zone=reservation.zone,
              block_name=reservation.block_name,
              sub_block_name=sub_block.name,
          ),
          available_slices=(sub_block.count - sub_block.in_use_count)
          // required_hosts,
      )
      for sub_block in sub_blocks
  ]
  return available_capacities, 0


def _get_blocks_in_reservation(
    reservation: ReservationLink,
) -> tuple[list[BlockReservationLink], int]:
  """Get blocks in a reservation."""
  command = (
      f'gcloud beta compute reservations blocks list {reservation.name} '
      f'--project={reservation.project} '
      f'--zone={reservation.zone} '
      '--format="value(name)"'
  )
  return_code, output = run_command_for_value(
      command,
      f'Get blocks in reservation {reservation.name}',
      dry_run_return_val='block0',
  )
  if return_code != 0:
    xpk_print(
        f'Get blocks in reservation {reservation.name} failed with'
        f' {return_code}'
    )
    return [], return_code

  return [
      BlockReservationLink(
          project=reservation.project,
          name=reservation.name,
          zone=reservation.zone,
          block_name=name,
      )
      for name in output.strip().splitlines()
      if name
  ], 0


def _calculate_target_accelerator_type(
    link: ReservationLink, system: SystemCharacteristics
) -> str:
  reservation_accelerator_type = system.reservation_accelerator_type
  assert reservation_accelerator_type

  if system.accelerator_type == AcceleratorType.TPU:
    project_number = project_id_to_project_number(link.project)
    return (
        f'projects/{project_number}/zones/{link.zone}/acceleratorTypes/'
        f'{reservation_accelerator_type}'
    )
  else:
    return reservation_accelerator_type


def _verify_reservation_configuration(
    reservation: _Reservation, system: SystemCharacteristics
) -> bool:
  """Checks if the reservation matches the system requirements.

  Args:
    reservation: The reservation object.
    system: The system characteristics.

  Returns:
    True if valid, False otherwise. Prints error message on failure.
  """
  if not reservation.specificReservation:
    return True

  if is_dry_run() and not reservation.specificReservation.machine_type:
    return True

  if system.accelerator_type == AcceleratorType.TPU:
    if reservation.specificReservation.machine_type != system.gce_machine_type:
      xpk_print(
          f"ERROR: Reservation '{reservation.name}' has machine type"
          f" '{reservation.specificReservation.machine_type}', but requested"
          f" system requires '{system.gce_machine_type}'."
      )
      return False
  elif system.accelerator_type == AcceleratorType.GPU:
    target_accel = system.reservation_accelerator_type
    has_matching_accelerator = any(
        acc.acceleratorType == target_accel
        for acc in reservation.specificReservation.guest_accelerators
    )
    if not has_matching_accelerator:
      xpk_print(
          f"ERROR: Reservation '{reservation.name}' does not have a matching"
          f" guest accelerator for '{target_accel}'."
      )
      return False
  return True


def _get_reservation_count(
    reservation: _Reservation,
    required_hosts: int,
    system: SystemCharacteristics,
    link: ReservationLink,
) -> tuple[int, int]:
  """Get capacity count of a reservation.

  Args:
    reservation: The reservation object.
    required_hosts: number of hosts required per slice.
    system: The system characteristics of the accelerator type.
    link: The reservation link (for logging/identification).

  Returns:
    Number of available slots in the reservation.
  """
  count = 0
  in_use_count = 0

  if reservation.specificReservation:
    count = int(reservation.specificReservation.count)
    in_use_count = int(reservation.specificReservation.inUseCount)
  elif reservation.aggregateReservation:
    reserved_resources = reservation.aggregateReservation.reservedResources
    target_accelerator_type = _calculate_target_accelerator_type(link, system)
    count = next(
        (
            r.acceleratorCount
            for r in reserved_resources
            if r.acceleratorType == target_accelerator_type
        ),
        0,
    )

    in_use_resources = reservation.aggregateReservation.inUseResources
    in_use_count = next(
        (
            r.acceleratorCount
            for r in in_use_resources
            if r.acceleratorType == target_accelerator_type
        ),
        0,
    )

  available_hosts = max(0, count - in_use_count)
  return available_hosts // required_hosts, 0
