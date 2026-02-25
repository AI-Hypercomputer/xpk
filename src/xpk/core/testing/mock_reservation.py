"""
Copyright 2026 Google LLC

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
from typing import Any

from ..reservation import (
    SpecificReservation,
    AggregateReservation,
    AcceleratorResource,
)
from .commands_tester import CommandsTester


@dataclass(frozen=True)
class MockSubBlock:
  count: int
  in_use_count: int
  name: str = 'sub-block'

  def to_dict(self) -> dict[str, Any]:
    return {
        'name': self.name,
        'count': self.count,
        'inUseCount': self.in_use_count,
    }


@dataclass(frozen=True)
class MockBlock:
  name: str = 'block'
  sub_blocks: list[MockSubBlock] = field(default_factory=list)


def _accelerator_resource_to_dict(
    resource: AcceleratorResource,
) -> dict[str, Any]:
  return {
      'accelerator': {
          'acceleratorType': resource.accelerator_type,
          'acceleratorCount': resource.accelerator_count,
      }
  }


def _aggregate_reservation_to_dict(
    reservation: AggregateReservation,
) -> dict[str, Any]:
  return {
      'reservedResources': [
          _accelerator_resource_to_dict(r)
          for r in reservation.reserved_resources
      ],
      'inUseResources': [
          _accelerator_resource_to_dict(r) for r in reservation.in_use_resources
      ],
  }


def _specific_reservation_to_dict(
    reservation: SpecificReservation,
) -> dict[str, Any]:
  instance_props: dict[str, Any] = {'machineType': reservation.machine_type}
  if reservation.guest_accelerators:
    instance_props['guestAccelerators'] = [
        {'acceleratorType': acc.accelerator_type}
        for acc in reservation.guest_accelerators
    ]

  return {
      'count': reservation.count,
      'inUseCount': reservation.in_use_count,
      'instanceProperties': instance_props,
  }


def setup_mock_reservation(
    commands_tester: CommandsTester,
    specific_reservation: SpecificReservation | None = None,
    aggregate_reservation: AggregateReservation | None = None,
    status: str = 'READY',
    blocks: list[MockBlock] | None = None,
):
  if aggregate_reservation:
    describe_json: dict[str, Any] = {
        'status': status,
        'aggregateReservation': _aggregate_reservation_to_dict(
            aggregate_reservation
        ),
    }
  else:
    if specific_reservation is None:
      specific_reservation = SpecificReservation(
          count=0, in_use_count=0, machine_type='test-machine'
      )
    describe_json = {
        'status': status,
        'specificReservation': _specific_reservation_to_dict(
            specific_reservation
        ),
    }

  commands_tester.set_result_for_command(
      (0, json.dumps(describe_json)),
      'gcloud beta compute reservations describe',
  )

  if blocks is not None:
    block_names = [b.name for b in blocks]
    commands_tester.set_result_for_command(
        (0, '\n'.join(block_names)),
        'gcloud beta compute reservations blocks list',
    )

    for block in blocks:
      commands_tester.set_result_for_command(
          (0, json.dumps([sb.to_dict() for sb in block.sub_blocks])),
          'gcloud beta compute reservations sub-blocks list',
          f'--block-name={block.name}',
      )
