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
from dataclasses import dataclass
from typing import Sequence

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
class ReservationCapacity:
  reservation: ReservationLink
  available_slices: int


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
) -> tuple[list[ReservationCapacity], int]:
  """Assess the available slices in the reservations.

  Args:
    reservations: list of reservations to assess.
    force_sub_block_targeting: if `True`, then the passed `ReservationLink` or `BlockReservationLink` will be flattened to adequate sub-blocks.
    required_hosts: number of hosts required per slice.

  Returns:
    List of capacity reservations with available slices.
  """
  reservation_capacities = []
  for reservation in reservations:
    capacities, return_code = _assess_available_slices_for_reservation(
        reservation, force_sub_block_targeting, required_hosts
    )
    if return_code != 0:
      return [], return_code
    reservation_capacities.extend(capacities)
  return reservation_capacities, 0


def _assess_available_slices_for_reservation(
    reservation: ReservationLink,
    force_sub_block_targeting: bool,
    required_hosts: int,
) -> tuple[list[ReservationCapacity], int]:
  """Assess the available slices for a single reservation.

  Args:
    reservation: reservation to assess.
    force_sub_block_targeting: if `True`, then the passed `ReservationLink` or `BlockReservationLink` will be flattened to adequate sub-blocks.
    required_hosts: number of hosts required per slice.

  Returns:
    List of available reservations (targeting sub-blocks if applicable).
  """
  if isinstance(reservation, SubBlockReservationLink):
    available_slices, return_code = _get_available_slices_in_sub_block(
        reservation, required_hosts
    )
    if return_code != 0:
      return [], return_code
    if available_slices > 0:
      return [ReservationCapacity(reservation, available_slices)], 0
    else:
      xpk_print(
          f'WARNING: Sub-block {reservation.sub_block_name} is either'
          ' unhealthy or not fitting. Skipping.'
      )
      return [], 0

  if isinstance(reservation, BlockReservationLink):
    return _get_healthy_and_fitting_sub_blocks_in_block(
        reservation, required_hosts
    )

  if force_sub_block_targeting:
    blocks, return_code = _get_blocks_in_reservation(reservation)
    if return_code != 0:
      return [], return_code
    if blocks:
      return assess_available_slices(
          blocks, force_sub_block_targeting, required_hosts
      )

    xpk_print(
        'WARNING: Super-slicing is enabled, but no blocks found in'
        f' reservation {reservation.name}. Skipping.'
    )
    return [], 0

  count, return_code = _get_reservation_count(reservation, required_hosts)
  if return_code != 0:
    return [], return_code
  return ([ReservationCapacity(reservation, count)] if count > 0 else []), 0


def _get_available_slices_in_sub_block(
    reservation: SubBlockReservationLink,
    required_hosts: int,
) -> tuple[int, int]:
  """Check if a sub-block is healthy and return available slices."""
  command = (
      'gcloud beta compute reservations sub-blocks list'
      f' {reservation.name} --block-name={reservation.block_name} --project={reservation.project} --zone={reservation.zone} --filter="name={reservation.sub_block_name} AND'
      ' healthInfo.healthStatus=HEALTHY"'
      ' --format="csv[no-heading](count,inUseCount)"'
  )
  return_code, output = run_command_for_value(
      command,
      f'Check sub-block {reservation.sub_block_name} health',
      dry_run_return_val='16,0',
  )
  if return_code != 0:
    return 0, return_code

  rows = _parse_csv_output(output, ['count', 'inUseCount'])
  if not rows:
    # If no output, it means the sub-block is not healthy/fitting.
    return 0, 0

  try:
    row = rows[0]
    count = int(row['count'])
    in_use_count = int(row['inUseCount'])
    available_slices = (count - in_use_count) // required_hosts
    return available_slices, 0
  except ValueError:
    xpk_print(f'Error: Unrecognized output format: "{output}".')
    return 0, 1


def _get_dry_run_value(
    env_var_name: str, reservation: ReservationLink, default: str = ''
) -> str:
  """Get a value from an environment variable for dry runs."""
  env_val = os.getenv(env_var_name)
  if not env_val:
    return default

  res_path = to_reservation_path(reservation, reservation.project)
  for item in env_val.split(';'):
    if '=' not in item:
      continue
    key, val = item.split('=', 1)
    if key.strip() == res_path:
      # For CSV/multiline data, we might use ':' as a line separator in env vars
      return val.strip().replace(':', '\n')

  return default


def _get_dry_run_sub_blocks(reservation: BlockReservationLink) -> str:
  """Get dry run sub-blocks based on environment variable."""
  return _get_dry_run_value(
      'DRY_RUN_RESERVATION_SUB_BLOCKS',
      reservation,
      default='',
  )


def _parse_csv_output(
    output: str, expected_fields: Sequence[str]
) -> list[dict[str, str]]:
  """Parses CSV output into a list of dictionaries.

  Args:
    output: The CSV output string from a command.
    expected_fields: List of field names corresponding to the CSV columns.

  Returns:
    A list of dictionaries, where each dictionary represents a row and maps
    field names to their values. Empty lines are skipped. Rows that don't
    match the number of expected fields are ignored.
  """
  results = []
  for line in output.strip().splitlines():
    line = line.strip()
    if not line:
      continue
    parts = [p.strip() for p in line.split(',')]
    if len(parts) == len(expected_fields):
      results.append(dict(zip(expected_fields, parts)))
  return results


def _get_healthy_and_fitting_sub_blocks_in_block(
    reservation: BlockReservationLink,
    required_hosts: int,
) -> tuple[list[ReservationCapacity], int]:
  """Get healthy and fitting sub-blocks in a block."""
  command = (
      f'gcloud beta compute reservations sub-blocks list {reservation.name} '
      f'--block-name={reservation.block_name} '
      f'--project={reservation.project} '
      f'--zone={reservation.zone} '
      '--filter="healthInfo.healthStatus=HEALTHY" '
      '--format="csv[no-heading](name,count,inUseCount)"'
  )
  return_code, output = run_command_for_value(
      command,
      f'Count healthy fitting sub-blocks in {reservation.block_name}',
      dry_run_return_val=_get_dry_run_sub_blocks(reservation),
  )
  if return_code != 0:
    return [], return_code

  available_capacities = []
  lines = output.strip().splitlines()
  # Handle old dry-run format where sub-blocks are comma-separated on one line
  if len(lines) == 1 and ',' in lines[0]:
    parts = [p.strip() for p in lines[0].split(',')]
    # If it doesn't look like CSV (name, count, inUseCount), treat as list of names
    if not (len(parts) >= 3 and parts[1].isdigit()):
      lines = parts

  for line in lines:
    if not line:
      continue

    rows = _parse_csv_output(line, ['name', 'count', 'inUseCount'])
    if rows and rows[0]['count'].isdigit():
      row = rows[0]
      name = row['name']
      count = int(row['count'])
      in_use_count = int(row['inUseCount'])
    else:
      # Legacy format: just a list of names
      name = line.strip().split(',')[0]
      count = required_hosts
      in_use_count = 0

    available_slots = (count - in_use_count) // required_hosts
    if available_slots > 0:
      available_capacities.append(
          ReservationCapacity(
              SubBlockReservationLink(
                  project=reservation.project,
                  name=reservation.name,
                  zone=reservation.zone,
                  block_name=reservation.block_name,
                  sub_block_name=name,
              ),
              available_slots,
          )
      )

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
      dry_run_return_val='',
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


def _get_reservation_count(
    reservation: ReservationLink, required_hosts: int
) -> tuple[int, int]:
  """Get capacity count of a reservation.

  Args:
    reservation: reservation to get count for.
    required_hosts: number of hosts required per slice.

  Returns:
    Number of available slots in the reservation.
  """
  command = (
      f'gcloud beta compute reservations describe {reservation.name} '
      f'--project={reservation.project} '
      f'--zone={reservation.zone} '
      '--format="csv[no-heading](specificReservation.count,specificReservation.inUseCount,status)"'
  )

  return_code, output = run_command_for_value(
      command,
      f'Get reservation count for {reservation.name}',
      dry_run_return_val='16,0,READY',
  )
  if return_code != 0:
    return 0, return_code

  rows = _parse_csv_output(output, ['count', 'in_use_count', 'status'])
  if not rows:
    return 0, 0

  try:
    row = rows[0]
    if row['status'] == 'READY':
      available_hosts = max(0, int(row['count']) - int(row['in_use_count']))
      return available_hosts // required_hosts, 0
  except ValueError:
    pass
  return 0, 0
