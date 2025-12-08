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


@dataclass
class Reservation:
  project: str
  name: str
  block_name: str | None = None
  sub_block_name: str | None = None


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
    return_code = verify_reservation_exists(args)
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
    reservation_path: str, zone: str, project: str
) -> str:
  """Get reservation maintenance interval.

  Args:
    args: user provided arguments for running the command.

  Returns:
    0 if successful and 1 otherwise.
  """
  reservation = parse_reservation(reservation_path, project)
  command = (
      f'gcloud beta compute reservations describe {reservation.name}'
      f' --project={reservation.project} --zone={zone} --format="value(specificReservation.instanceProperties.maintenanceInterval)"'
  )
  return_code, output = run_command_for_value(
      command, 'Get reservation maintenance interval'
  )
  if return_code != 0:
    xpk_print(f'Get reservation maintenance interval ERROR {return_code}')
    xpk_exit(1)
  return output.strip()


def get_reservation_placement_policy(
    reservation_path: str, zone: str, project: str
) -> str:
  """Get reservation placement policy.

  Args:
    args: user provided arguments for running the command.

  Returns:
    0 if successful and 1 otherwise.
  """
  reservation = parse_reservation(reservation_path, project)
  command = (
      f'gcloud beta compute reservations describe {reservation.name}'
      f' --project={reservation.project} --zone={zone} --format="value(resourcePolicies.policy)"'
  )
  return_code, output = run_command_for_value(
      command, 'Get reservation placement policy'
  )
  if return_code != 0:
    xpk_print(f'Get reservation placement policy ERROR {return_code}')
    xpk_exit(1)
  return output.strip()


def get_reservation_deployment_type(
    reservation_path: str, zone: str, project: str
) -> str:
  """Get reservation deployment type."""
  reservation = parse_reservation(reservation_path, project)
  command = (
      f'gcloud beta compute reservations describe {reservation.name}'
      f' --project={reservation.project} --zone={zone} --format="value(deploymentType)"'
  )
  return_code, output = run_command_for_value(
      command, 'Get reservation deployment type', dry_run_return_val='DENSE'
  )
  if return_code != 0:
    xpk_print(f'Get reservation deployment type ERROR {return_code}')
    xpk_exit(1)
  return output.strip()


def verify_reservation_exists(args) -> int:
  """Verify the reservation exists.

  Args:
    args: user provided arguments for running the command.

  Returns:
    0 if successful and 1 otherwise.
  """
  reservation = parse_reservation(args.reservation, args.project)
  command = (
      f'gcloud beta compute reservations describe {reservation.name}'
      f' --project={reservation.project} --zone={args.zone}'
  )
  return_code = run_command_with_updates(command, 'Describe reservation')
  if return_code != 0:
    xpk_print(f'Describe reservation returned ERROR {return_code}')
    xpk_print('Please confirm that your reservation name is correct.')
    return 1
  return 0


def get_capacity_arguments_from_capacity_type(
    args,
    capacity_type: CapacityType,
    max_nodes: int,
    accelerator_type: AcceleratorType,
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
          f'--reservation-affinity=specific --reservation={args.reservation}'
      )
    case _:
      xpk_print(
          f'Unknown capacity type: {capacity_type}. Unable to determine'
          ' capacity args.'
      )
      return_code = 1
  return capacity_args, return_code


def get_capacity_node_selectors_from_capacity_type(
    args, capacity_type: str
) -> tuple[str, int]:
  """Determine the node selectors for a workload to run on a specific capacity type.

  Args:
    args: user provided arguments for running the command.
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
    case CapacityType.FLEX_START.name:
      node_selector = 'cloud.google.com/gke-queued: "true"'
    case CapacityType.SPOT.name:
      node_selector = 'cloud.google.com/gke-spot: "true"'
    case CapacityType.RESERVATION.name:
      node_selector = f'cloud.google.com/reservation-name: {args.reservation}'
    case _:
      xpk_print(
          f'Unknown capacity type: {capacity_type}. Unable to determine the'
          ' node selectors.'
      )
      return_code = 1
  return node_selector, return_code


def parse_reservation(
    reservation_path: str, cluster_project: str
) -> Reservation:
  """Parses the reservation details from the reservation path.
      Also supports reservation blocks and sub-blocks.
      Assumes cluster project if project is not contained in the path.

      Args:
        reservation_path: path to the reservation, reservation block or sub-block in format:
  `[projects/RESERVATION_PROJECT_ID/reservations/]RESERVATION_NAME[/reservationBlocks/BLOCK_NAME[/reservationSubBlocks/SUB_BLOCK_NAME]]`
        cluster_project: the cluster project

      Returns:
        Reservation instance containing reservation details.
  """
  reservation = _try_parse_reservation(reservation_path, cluster_project)
  if reservation is None:
    xpk_print('Unable to parse reservation: ', reservation_path)
    xpk_exit(1)
  return reservation


def _try_parse_reservation(
    reservation_path: str, cluster_project: str
) -> Reservation | None:
  # assume trivial case, path contains just the reservation name
  reservation = Reservation(
      project=cluster_project,
      name=reservation_path,
      block_name=None,
      sub_block_name=None,
  )
  parts = reservation_path.split('/')
  if min(map(len, parts)) == 0:  # all parts must be non-empty
    return None
  if len(parts) == 1:
    return reservation  # trivial case

  if parts[0] == 'projects':
    reservation.project = parts[1]
    if len(parts) < 4 or parts[2] != 'reservations':
      return None
    parts = parts[3:]  # remove projects/PROJECT/reservations/ prefix

  if len(parts) not in (1, 3, 5):
    return None
  reservation.name = parts[0]
  if len(parts) >= 3:
    if parts[1] != 'reservationBlocks':
      return None
    reservation.block_name = parts[2]
    if len(parts) >= 5:
      if parts[3] != 'reservationSubBlocks':
        return None
      reservation.sub_block_name = parts[4]
  return reservation
