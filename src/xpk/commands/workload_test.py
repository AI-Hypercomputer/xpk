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

import dataclasses
from unittest.mock import MagicMock, patch
import pytest
from ..core.system_characteristics import SystemCharacteristics
from .workload import _validate_sub_slicing_topology


SYSTEM_CHARACTERISTICS = SystemCharacteristics(
    topology='8x8',
    vms_per_slice=1,
    gke_accelerator='nvidia-l4',
    gce_machine_type='g2-standard-12',
    chips_per_vm=1,
    accelerator_type=1,
    device_type='l4-1',
    supports_sub_slicing=True,
    requires_workload_policy=False,
)


@pytest.fixture(autouse=True)
def xpk_print(mocker):
  return mocker.patch('xpk.commands.workload.xpk_print')


def test_validate_sub_slicing_topology_exits_for_unsupported_topology(
    xpk_print,
):
  with pytest.raises(SystemExit):
    _validate_sub_slicing_topology(SYSTEM_CHARACTERISTICS, '2x1')

  assert (
      'shape is invalid. It has to be one of' in xpk_print.mock_calls[0].args[0]
  )


def test_validate_sub_slicing_topology_exits_for_too_large_topology(xpk_print):
  with pytest.raises(SystemExit):
    _validate_sub_slicing_topology(SYSTEM_CHARACTERISTICS, '16x16')

  assert (
      'shape is too large. The shape cannot be'
      in xpk_print.mock_calls[0].args[0]
  )


def test_validate_sub_slicing_topology_does_nothing_for_supported_topology():
  _validate_sub_slicing_topology(SYSTEM_CHARACTERISTICS, '4x4')


@patch('xpk.commands.common.xpk_print')
def test_validate_sub_slicing_topology_fails_for_unsupported_system(
    common_xpk_print: MagicMock,
):
  unsupported_system = dataclasses.replace(
      SYSTEM_CHARACTERISTICS, supports_sub_slicing=False
  )

  with pytest.raises(SystemExit):
    _validate_sub_slicing_topology(unsupported_system, '4x4')

  assert (
      'l4-1 does not support Sub-slicing.'
      in common_xpk_print.mock_calls[0].args[0]
  )
