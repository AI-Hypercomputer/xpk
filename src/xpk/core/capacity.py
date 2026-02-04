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
  available_count: int


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
    return_code = run_command_with_updates(command, 'Describe reservation')
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
    capacity_type: str, reservation: ReservationLink | None
) -> tuple[str, int]:
  """Determine the node selectors for a workload to run on a specific capacity type.

  Args:
    capacity_type: The type of capacity the user configured.
    reservation: The reservation to use. Set to None if not
      using reservations.

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
      reservation_name = to_reservation_path(reservation)
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
    parts = parts[3:]

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


def to_reservation_path(reservation: ReservationLink) -> str:
  """Convert reservation to path string."""
  path = reservation.name
  if isinstance(reservation, BlockReservationLink):
    path += f'/reservationBlocks/{reservation.block_name}'
    if isinstance(reservation, SubBlockReservationLink):
      path += f'/reservationSubBlocks/{reservation.sub_block_name}'
  return path


def assess_available_slices(
    reservations: list[ReservationLink],
    enable_super_slicing: bool,
) -> list[ReservationCapacity]:
  """Assess the available slices in the reservations.

  Args:
    reservations: list of reservations to assess.
    enable_super_slicing: whether to check for super-slicing blocks.

  Returns:
    List of capacity reservations with available slices.
  """
  expanded_reservations = []
  for reservation in reservations:
    expanded_reservations.extend(
        _assess_available_slices_for_reservation(
            reservation, enable_super_slicing
        )
    )
  return expanded_reservations


def _assess_available_slices_for_reservation(
    reservation: ReservationLink,
    enable_super_slicing: bool,
) -> list[ReservationCapacity]:
  """Assess the available slices for a single reservation.

  Args:
    reservation: reservation to assess.
    enable_super_slicing: whether to check for super-slicing blocks.

  Returns:
    List of available reservations (targeting sub-blocks if applicable).
  """
  if isinstance(reservation, SubBlockReservationLink):
    return (
        [ReservationCapacity(reservation, 1)]
        if _is_sub_block_healthy_and_unused(reservation)
        else []
    )

  if isinstance(reservation, BlockReservationLink):
    return _get_healthy_and_unused_sub_blocks_in_block(reservation)

  # If super-slicing is enabled, check for blocks first
  if enable_super_slicing:
    blocks = _get_blocks_in_reservation(reservation)
    if blocks:
      slices = []
      for block in blocks:
        slices.extend(_get_healthy_and_unused_sub_blocks_in_block(block))
      return slices

  # Otherwise (or if no blocks found), use reservation count
  count = _get_reservation_count(reservation)
  return [ReservationCapacity(reservation, count)] if count > 0 else []


def _is_sub_block_healthy_and_unused(
    reservation: SubBlockReservationLink,
) -> bool:
  """Check if a sub-block is healthy and unused."""
  command = (
      'gcloud beta compute reservations sub-blocks list'
      f' {reservation.name} --block-name={reservation.block_name} --project={reservation.project} --zone={reservation.zone} --filter="name={reservation.sub_block_name} AND'
      ' inUseCount=0 AND healthInfo.healthStatus=HEALTHY"'
      ' --format="value(name)"'
  )
  return_code, output = run_command_for_value(
      command,
      f'Check sub-block {reservation.sub_block_name} health',
      dry_run_return_val=reservation.sub_block_name,
  )
  return return_code == 0 and bool(output.strip())


def _get_dry_run_list(
    env_var_name: str, reservation: ReservationLink, default: str = ''
) -> str:
  """Get a newline-separated list from an environment variable for dry runs."""
  env_val = os.getenv(env_var_name)
  if not env_val:
    return default

  res_path = to_reservation_path(reservation)
  for item in env_val.split(';'):
    if '=' not in item:
      continue
    key, val = item.split('=', 1)
    if key.strip() == res_path:
      return val.replace(',', '\n')

  return default


def _get_dry_run_sub_blocks(reservation: BlockReservationLink) -> str:
  """Get dry run sub-blocks based on environment variable."""
  return _get_dry_run_list(
      'DRY_RUN_RESERVATION_SUB_BLOCKS', reservation, default='sub1\nsub2'
  )


def _get_healthy_and_unused_sub_blocks_in_block(
    reservation: BlockReservationLink,
) -> list[ReservationCapacity]:
  """Get healthy and unused sub-blocks in a block."""
  command = (
      f'gcloud beta compute reservations sub-blocks list {reservation.name} '
      f'--block-name={reservation.block_name} '
      f'--project={reservation.project} '
      f'--zone={reservation.zone} '
      '--filter="inUseCount=0 AND healthInfo.healthStatus=HEALTHY" '
      '--format="value(name)"'
  )
  return_code, output = run_command_for_value(
      command,
      f'Count healthy unused sub-blocks in {reservation.block_name}',
      dry_run_return_val=_get_dry_run_sub_blocks(reservation),
  )
  if return_code != 0:
    return []

  return [
      ReservationCapacity(
          SubBlockReservationLink(
              project=reservation.project,
              name=reservation.name,
              zone=reservation.zone,
              block_name=reservation.block_name,
              sub_block_name=name,
          ),
          1,
      )
      for name in output.strip().splitlines()
      if name
  ]


def _get_dry_run_blocks(reservation: ReservationLink) -> str:
  """Get dry run blocks based on environment variable."""
  return _get_dry_run_list('DRY_RUN_RESERVATION_BLOCKS', reservation)


def _get_blocks_in_reservation(
    reservation: ReservationLink,
) -> list[BlockReservationLink]:
  """Get blocks in a reservation."""
  command = (
      'gcloud beta compute reservations blocks list'
      f' --reservation={reservation.name} '
      f'--project={reservation.project} '
      f'--zone={reservation.zone} '
      '--format="value(name)"'
  )
  return_code, output = run_command_for_value(
      command,
      f'Get blocks in reservation {reservation.name}',
      dry_run_return_val=_get_dry_run_blocks(reservation),
  )
  if return_code != 0:
    return []

  return [
      BlockReservationLink(
          project=reservation.project,
          name=reservation.name,
          zone=reservation.zone,
          block_name=name,
      )
      for name in output.strip().splitlines()
      if name
  ]


def _get_reservation_count(reservation: ReservationLink) -> int:
  """Get capacity count of a reservation.

  Args:
    reservation: reservation to get count for.

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
      dry_run_return_val='1,0,READY',
  )
  if return_code != 0:
    return 0

  try:
    count_str, in_use_str, status = output.strip().split(',')
    if status == 'READY':
      return max(0, int(count_str) - int(in_use_str))
  except (ValueError, IndexError):
    pass
  return 0
