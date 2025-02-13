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

from ..utils.console import xpk_print
from .commands import run_command_with_updates

AUTOPROVISIONING_CONFIG_VALUE = 'AUTOPROVISION'
AUTOPROVISIONING_CONFIG_MINIMUM_KEY = 'minimum_chips'
AUTOPROVISIONING_CONFIG_MAXIMUM_KEY = 'maximum_chips'
CAPACITY_TYPE_CONFIG_KEY = 'capacity_type'
RESERVATION_CONFIG_KEY = 'reservation_id'


class CapacityType(enum.Enum):
  ON_DEMAND = 'on_demand'
  RESERVATION = 'reservation'
  SPOT = 'spot'
  UNKNOWN = 'unknown'


class DeviceType(enum.Enum):
  H100 = 'h100-80gb-8'
  H100_MEGA = 'h100-mega-80gb-8'
  H200 = 'h200-141gb-8'


class CapacityManager:
  """Manages capacity-related operations such as reservations and node selectors."""

  def __init__(self, args):
    self.args = args

  def print_reservations(self) -> int:
    """Print the reservations in the project.

    Returns:
      0 if successful and 1 otherwise.
    """
    command = (
        f'gcloud beta compute reservations list --project={self.args.project}'
    )
    return_code = run_command_with_updates(
        command, 'Get all reservations in the project', self.args
    )
    if return_code != 0:
      xpk_print(f'Get all reservations returned ERROR {return_code}')
      return 1

    return 0

  def get_capacity_type(self) -> tuple[CapacityType, int]:
    """Determine the capacity type based on user arguments.

    Returns:
      Tuple with string with the system characteristics and
      int of 0 if successful and 1 otherwise.
    """
    capacity_type = CapacityType.UNKNOWN
    num_types = 0
    return_code = 0

    # Determine the capacity argument.
    if self.args.on_demand:
      capacity_type = CapacityType.ON_DEMAND
      num_types += 1

    if self.args.reservation:
      return_code = self.verify_reservation_exists()
      if return_code > 0:
        return capacity_type, return_code
      capacity_type = CapacityType.RESERVATION
      num_types += 1

    if self.args.spot:
      capacity_type = CapacityType.SPOT
      num_types += 1

    # Check that the number of user arguments provided is valid.
    if num_types == 0:
      capacity_type = CapacityType.UNKNOWN
    elif num_types != 1:
      xpk_print(
          'ERROR: User specified more than one of the following arguments.'
          ' Please specify only one of `--reservation=$RESERVATION_NAME`,'
          ' `--on-demand` or `--spot`.'
      )
      return_code = 1

    return capacity_type, return_code

  def verify_reservation_exists(self) -> int:
    """Verify the reservation exists.

    Returns:
      0 if successful and 1 otherwise.
    """
    command = (
        f'gcloud beta compute reservations describe {self.args.reservation}'
        f' --project={self.args.project} --zone={self.args.zone}'
    )
    return_code = run_command_with_updates(
        command, 'Describe reservation', self.args
    )
    if return_code != 0:
      xpk_print(f'Describe reservation returned ERROR {return_code}')
      xpk_print('Please confirm that your reservation name is correct.')
      return 1

    return 0

  def get_capacity_arguments(
      self, capacity_type: CapacityType
  ) -> tuple[str, int]:
    """Determine the TPU Nodepool creation capacity arguments needed.

    Args:
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
      case CapacityType.RESERVATION:
        capacity_args = (
            '--reservation-affinity=specific'
            f' --reservation={self.args.reservation}'
        )
      case _:
        xpk_print(
            f'Unknown capacity type: {capacity_type}. Unable to determine'
            ' capacity args.'
        )
        return_code = 1
    return capacity_args, return_code

  def get_capacity_node_selectors(self, capacity_type: str) -> tuple[str, int]:
    """Determine the node selectors for a workload to run on a specific capacity type.

    Args:
      capacity_type: The type of capacity the user configured.

    Returns:
      Tuple with string with the node selectors to use and
      int of 0 if successful and 1 otherwise.
    """
    node_selector = ''
    return_code = 0

    match capacity_type:
      case CapacityType.ON_DEMAND.name:
        node_selector = ''
      case CapacityType.SPOT.name:
        node_selector = 'cloud.google.com/gke-spot="true"'
      case CapacityType.RESERVATION.name:
        node_selector = (
            f'cloud.google.com/reservation-name: {self.args.reservation}'
        )
      case _:
        xpk_print(
            f'Unknown capacity type: {capacity_type}. Unable to determine the'
            ' node selectors.'
        )
        return_code = 1
    return node_selector, return_code
