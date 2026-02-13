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

from dataclasses import dataclass

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
