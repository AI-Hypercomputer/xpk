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
from dataclasses import dataclass
from typing import Sequence, Any

from .commands import run_command_for_value
from .system_characteristics import AcceleratorType, SystemCharacteristics
from .gcloud_context import project_id_to_project_number
from ..utils.console import xpk_print
from ..utils.kueue import is_queued_cluster
from ..utils.execution_context import is_dry_run
from .reservation import (
    ReservationLink,
    BlockReservationLink,
    SubBlockReservationLink,
    Reservation,
    verify_reservations_exist,
    to_reservation_path,
    get_reservation_cached,
)

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


class CapacityType(enum.Enum):
  ON_DEMAND = 'on_demand'
  RESERVATION = 'reservation'
  SPOT = 'spot'
  UNKNOWN = 'unknown'
  FLEX_START = 'flex_start'


@dataclass(frozen=True)
class ReservationCapacity:
  reservation: ReservationLink
  available_slices: int


@dataclass(frozen=True)
class _ReservationSubBlock:
  name: str
  count: int
  in_use_count: int


def _parse_reservation_sub_block(data: dict[str, Any]) -> _ReservationSubBlock:
  return _ReservationSubBlock(
      name=str(data.get('name', '')),
      count=int(data.get('count', 0)),
      in_use_count=int(data.get('inUseCount', '0')),
  )


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
  parent_reservation = get_reservation_cached(reservation)

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
    reservation: Reservation, system: SystemCharacteristics
) -> bool:
  """Checks if the reservation matches the system requirements.

  Args:
    reservation: The reservation object.
    system: The system characteristics.

  Returns:
    True if valid, False otherwise. Prints error message on failure.
  """
  if not reservation.specific_reservation:
    return True

  if is_dry_run() and not reservation.specific_reservation.machine_type:
    return True

  if system.accelerator_type == AcceleratorType.TPU:
    if reservation.specific_reservation.machine_type != system.gce_machine_type:
      xpk_print(
          f"ERROR: Reservation '{reservation.name}' has machine type"
          f" '{reservation.specific_reservation.machine_type}', but requested"
          f" system requires '{system.gce_machine_type}'."
      )
      return False
  elif system.accelerator_type == AcceleratorType.GPU:
    target_accel = system.reservation_accelerator_type
    has_matching_accelerator = any(
        acc.accelerator_type == target_accel
        for acc in reservation.specific_reservation.guest_accelerators
    )
    if not has_matching_accelerator:
      xpk_print(
          f"ERROR: Reservation '{reservation.name}' does not have a matching"
          f" guest accelerator for '{target_accel}'."
      )
      return False
  return True


def _get_reservation_count(
    reservation: Reservation,
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

  if reservation.specific_reservation:
    count = int(reservation.specific_reservation.count)
    in_use_count = int(reservation.specific_reservation.in_use_count)
  elif reservation.aggregate_reservation:
    reserved_resources = reservation.aggregate_reservation.reserved_resources
    target_accelerator_type = _calculate_target_accelerator_type(link, system)
    count = next(
        (
            r.accelerator_count
            for r in reserved_resources
            if r.accelerator_type == target_accelerator_type
        ),
        0,
    )

    in_use_resources = reservation.aggregate_reservation.in_use_resources
    in_use_count = next(
        (
            r.accelerator_count
            for r in in_use_resources
            if r.accelerator_type == target_accelerator_type
        ),
        0,
    )

  available_hosts = max(0, count - in_use_count)
  return available_hosts // required_hosts, 0
