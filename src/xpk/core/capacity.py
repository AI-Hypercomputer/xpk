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
from dataclasses import dataclass
from typing import Sequence

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
    get_reservation,
    get_reservation_accelerator_type,
    list_healthy_sub_blocks,
    get_blocks_in_reservation,
    AcceleratorResource,
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
    system: SystemCharacteristics,
    vms_per_slice: int,
    validate_reservations: bool = True,
) -> tuple[list[ReservationCapacity], int]:
  """Assess the available slices in the reservations.

  Args:
    reservations: list of reservations to assess.
    force_sub_block_targeting: if `True`, then the passed `ReservationLink` or `BlockReservationLink` will be flattened to adequate sub-blocks.
    system: The system characteristics of the accelerator type.
    vms_per_slice: The number of VMs required per slice.
    validate_reservations: if `True`, validates the reservation exists and configuration matches.

  Returns:
    List of capacity reservations with available slices.
  """
  reservation_capacities = []
  for reservation in reservations:
    if validate_reservations:
      parent_reservation = get_reservation(reservation)

      if not parent_reservation:
        xpk_print(f"ERROR: Failed to fetch reservation '{reservation.name}'.")
        return [], 1

      if not _verify_reservation_configuration(parent_reservation, system):
        return [], 1

    capacities, return_code = _assess_available_slices_for_reservation(
        reservation, force_sub_block_targeting, system, vms_per_slice
    )
    if return_code != 0:
      return [], return_code
    if not capacities and validate_reservations:
      xpk_print(
          'Warning: Reservation'
          f' {to_reservation_path(reservation, reservation.project)} has no'
          ' available capacity.'
      )
    reservation_capacities.extend(capacities)

  # Deduplicate reservation_capacities, preserving order:
  reservation_capacities = list(dict.fromkeys(reservation_capacities))

  return reservation_capacities, 0


def _assess_available_slices_for_reservation(
    reservation: (
        ReservationLink | BlockReservationLink | SubBlockReservationLink
    ),
    force_sub_block_targeting: bool,
    system: SystemCharacteristics,
    vms_per_slice: int,
) -> tuple[list[ReservationCapacity], int]:
  """Assess the available slices for a single reservation.

  Args:
    reservation: reservation to assess.
    force_sub_block_targeting: if `True`, then the passed `ReservationLink` or `BlockReservationLink` will be flattened to adequate sub-blocks.
    system: The system characteristics of the accelerator type.
    vms_per_slice: The number of VMs required per slice.

  Returns:
    List of available reservations (targeting sub-blocks if applicable).
  """
  if (
      isinstance(reservation, SubBlockReservationLink)
      or force_sub_block_targeting
      and isinstance(reservation, BlockReservationLink)
  ):
    return _assess_healthy_and_fitting_sub_blocks_in_block(
        reservation, vms_per_slice
    )
  elif force_sub_block_targeting:
    # reservation instanceof ReservationLink (not Block/SubBlock):
    blocks, return_code = get_blocks_in_reservation(reservation)
    if return_code != 0:
      return [], return_code
    if blocks:
      return assess_available_slices(
          blocks,
          force_sub_block_targeting,
          system,
          vms_per_slice=vms_per_slice,
          validate_reservations=False,
      )

    return [], 0

  slices_count, return_code = _get_reservation_slices_count(
      reservation, system, vms_per_slice
  )
  if return_code != 0:
    return [], return_code
  return (
      [ReservationCapacity(reservation, slices_count)]
      if slices_count > 0
      else []
  ), 0


def _assess_healthy_and_fitting_sub_blocks_in_block(
    reservation: BlockReservationLink | SubBlockReservationLink,
    required_hosts: int,
) -> tuple[list[ReservationCapacity], int]:
  """Get healthy and fitting sub-block capacities in a block. Also works for sub-block links."""
  sub_blocks, return_code = list_healthy_sub_blocks(reservation)

  if return_code != 0:
    return [], return_code

  available_capacities: list[ReservationCapacity] = [
      ReservationCapacity(
          sub_block.link,
          available_slices=(
              (sub_block.count - sub_block.in_use_count) // required_hosts
          ),
      )
      for sub_block in sub_blocks
  ]
  return [
      capacity
      for capacity in available_capacities
      if capacity.available_slices > 0
  ], 0


def _find_matching_accelerator_resource(
    reservation: Reservation, system: SystemCharacteristics
) -> AcceleratorResource | None:
  """Finds the matching accelerator resource in an aggregate reservation.

  Args:
    reservation: The reservation object.
    system: The system characteristics.

  Returns:
    The matching AcceleratorResource or None if not found.
  """
  reservation_accelerator_type = get_reservation_accelerator_type(system)
  assert reservation_accelerator_type

  if not reservation.aggregate_reservation:
    return None

  reserved_resources = reservation.aggregate_reservation.reserved_resources

  if system.accelerator_type == AcceleratorType.TPU:
    # Try with Project ID:
    target_type_id = (
        f'projects/{reservation.link.project}/zones/{reservation.link.zone}/'
        f'acceleratorTypes/{reservation_accelerator_type}'
    )
    for r in reserved_resources:
      if r.accelerator_type.lstrip('/') == target_type_id:
        return r

    # Try with Project Number:
    project_number = project_id_to_project_number(reservation.link.project)
    target_type_number = (
        f'projects/{project_number}/zones/{reservation.link.zone}/'
        f'acceleratorTypes/{reservation_accelerator_type}'
    )
    for r in reserved_resources:
      if r.accelerator_type.lstrip('/') == target_type_number:
        return r
  else:
    for r in reserved_resources:
      if r.accelerator_type == reservation_accelerator_type:
        return r

  return None


def _verify_reservation_configuration(
    reservation: Reservation,
    system: SystemCharacteristics,
) -> bool:
  """Checks if the reservation matches the system requirements.

  Args:
    reservation: The reservation object.
    system: The system characteristics.

  Returns:
    True if valid, False otherwise. Prints error message on failure.
  """
  if is_dry_run():
    return True

  if reservation.specific_reservation:
    if (
        system.accelerator_type == AcceleratorType.TPU
        or system.accelerator_type == AcceleratorType.CPU
    ):
      if (
          reservation.specific_reservation.machine_type
          != system.gce_machine_type
      ):
        xpk_print(
            f"Warning: Reservation '{reservation.link.name}' has machine type"
            f" '{reservation.specific_reservation.machine_type}', but requested"
            f" system requires '{system.gce_machine_type}'."
        )
        return False
    elif system.accelerator_type == AcceleratorType.GPU:
      target_accel = get_reservation_accelerator_type(system)
      has_matching_accelerator = any(
          acc.accelerator_type == target_accel
          for acc in reservation.specific_reservation.guest_accelerators
      )
      if not has_matching_accelerator:
        xpk_print(
            f"Warning: Reservation '{reservation.link.name}' does not have a"
            f" matching guest accelerator for '{target_accel}'."
        )
        return False
  elif reservation.aggregate_reservation:
    matching_resource = _find_matching_accelerator_resource(reservation, system)
    if not matching_resource:
      xpk_print(
          f"ERROR: Aggregate Reservation '{reservation.link.name}' does not"
          ' have a matching accelerator for'
          f" '{get_reservation_accelerator_type(system)}'."
      )
      return False
  return True


def _get_reservation_slices_count(
    reservation_link: ReservationLink,
    system: SystemCharacteristics,
    vms_per_slice: int,
) -> tuple[int, int]:
  """Get capacity count of a reservation.

  Args:
    reservation: The reservation object.
    system: The system characteristics of the accelerator type.
    vms_per_slice: The number of VMs required per slice.

  Returns:
    Number of available slots in the reservation.
  """
  reservation = get_reservation(reservation_link)
  if not reservation:
    return 0, 1

  count = 0
  in_use_count = 0
  divisor = 1

  if reservation.specific_reservation:
    count = int(reservation.specific_reservation.count)
    in_use_count = int(reservation.specific_reservation.in_use_count)
    divisor = vms_per_slice
  elif reservation.aggregate_reservation:
    matching_resource = _find_matching_accelerator_resource(reservation, system)
    assert matching_resource
    count = matching_resource.accelerator_count
    in_use_resources = reservation.aggregate_reservation.in_use_resources
    in_use_count = next(
        (
            r.accelerator_count
            for r in in_use_resources
            if r.accelerator_type == matching_resource.accelerator_type
        ),
        0,
    )
    divisor = vms_per_slice * system.chips_per_vm

  available_hosts = max(0, count - in_use_count)
  return available_hosts // divisor, 0
