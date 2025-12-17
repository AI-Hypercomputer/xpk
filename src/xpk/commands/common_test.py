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

import unittest
from unittest.mock import MagicMock, patch

from xpk.commands.common import is_GPU_TAS_possible
from xpk.core.capacity import (
    H100_DEVICE_TYPE,
    H100_MEGA_DEVICE_TYPE,
    CapacityType,
)
from xpk.core.system_characteristics import SystemCharacteristics


class CommonCommandsTest(unittest.TestCase):

  @patch("xpk.commands.common.run_command_for_value")
  @patch("xpk.commands.common.xpk_exit")
  @patch("xpk.commands.common.xpk_print")
  @patch("xpk.commands.common.is_dry_run")
  def test_is_GPU_TAS_possible_dry_run(
      self, mock_is_dry_run, mock_xpk_print, mock_xpk_exit, mock_run_command
  ):
    """Test is_GPU_TAS_possible returns True in dry_run mode."""
    mock_is_dry_run.return_value = True
    self.assertTrue(is_GPU_TAS_possible(None, None, "cluster", "zone", "project"))
    mock_is_dry_run.assert_called_once()
    mock_xpk_print.assert_not_called()
    mock_xpk_exit.assert_not_called()
    mock_run_command.assert_not_called()

  @patch("xpk.commands.common.is_dry_run", return_value=False)
  @patch("xpk.commands.common.xpk_exit")
  @patch("xpk.commands.common.xpk_print")
  def test_is_GPU_TAS_possible_no_system_characteristics(
      self, mock_xpk_print, mock_xpk_exit, mock_is_dry_run
  ):
    """Test is_GPU_TAS_possible exits if system_characteristics is None."""
    mock_xpk_exit.side_effect = SystemExit(1)
    with self.assertRaises(SystemExit):
      is_GPU_TAS_possible(None, MagicMock(), "cluster", "zone", "project")
    mock_xpk_print.assert_called_with(
        "system_characteristics data was not found in configmaps."
    )
    mock_xpk_exit.assert_called_with(1)

  @patch("xpk.commands.common.is_dry_run", return_value=False)
  @patch("xpk.commands.common.xpk_exit")
  @patch("xpk.commands.common.xpk_print")
  def test_is_GPU_TAS_possible_no_capacity_type(
      self, mock_xpk_print, mock_xpk_exit, mock_is_dry_run
  ):
    """Test is_GPU_TAS_possible exits if capacity_type is None."""
    mock_xpk_exit.side_effect = SystemExit(1)
    with self.assertRaises(SystemExit):
      is_GPU_TAS_possible(MagicMock(), None, "cluster", "zone", "project")
    mock_xpk_print.assert_called_with(
        "capacity_type data was not found in configmaps."
    )
    mock_xpk_exit.assert_called_with(1)

  @patch("xpk.commands.common.is_dry_run", return_value=False)
  def test_is_GPU_TAS_possible_h100_unsupported_capacity(self, mock_is_dry_run):
    """Test is_GPU_TAS_possible for H100 with unsupported capacity type."""
    mock_system = MagicMock(spec=SystemCharacteristics)
    mock_system.device_type = H100_DEVICE_TYPE
    self.assertFalse(
        is_GPU_TAS_possible(
            mock_system, CapacityType.ON_DEMAND, "cluster", "zone", "project"
        )
    )

    mock_system.device_type = H100_MEGA_DEVICE_TYPE
    self.assertFalse(
        is_GPU_TAS_possible(
            mock_system, CapacityType.ON_DEMAND, "cluster", "zone", "project"
        )
    )

  @patch("xpk.commands.common.is_dry_run", return_value=False)
  def test_is_GPU_TAS_possible_flex_start_capacity(self, mock_is_dry_run):
    """Test is_GPU_TAS_possible returns True for FLEX_START capacity."""
    mock_system = MagicMock(spec=SystemCharacteristics)
    mock_system.device_type = "some-device"
    self.assertTrue(
        is_GPU_TAS_possible(
            mock_system, CapacityType.FLEX_START, "cluster", "zone", "project"
        )
    )

  @patch("xpk.commands.common.run_command_for_value")
  @patch("xpk.commands.common.is_dry_run", return_value=False)
  def test_is_GPU_TAS_possible_compact_placement_exists(
      self, mock_is_dry_run, mock_run_command
  ):
    """Test is_GPU_TAS_possible with COMPACT placement returns True."""
    mock_system = MagicMock(spec=SystemCharacteristics)
    mock_system.device_type = "a3-ultra"
    mock_run_command.return_value = (0, "some-nodepool\nsome-other-nodepool\n")
    self.assertTrue(
        is_GPU_TAS_possible(
            mock_system,
            CapacityType.RESERVATION,
            "cluster",
            "zone",
            "project",
        )
    )

  @patch("xpk.commands.common.run_command_for_value")
  @patch("xpk.commands.common.is_dry_run", return_value=False)
  def test_is_GPU_TAS_possible_no_compact_placement(
      self, mock_is_dry_run, mock_run_command
  ):
    """Test is_GPU_TAS_possible without COMPACT placement returns False."""
    mock_system = MagicMock(spec=SystemCharacteristics)
    mock_system.device_type = "a3-ultra"
    mock_run_command.return_value = (0, "")
    self.assertFalse(
        is_GPU_TAS_possible(
            mock_system,
            CapacityType.RESERVATION,
            "cluster",
            "zone",
            "project",
        )
    )

  @patch("xpk.commands.common.xpk_print")
  @patch("xpk.commands.common.run_command_for_value")
  @patch("xpk.commands.common.is_dry_run", return_value=False)
  def test_is_GPU_TAS_possible_command_fails(
      self, mock_is_dry_run, mock_run_command, mock_xpk_print
  ):
    """Test is_GPU_TAS_possible when gcloud command fails."""
    mock_system = MagicMock(spec=SystemCharacteristics)
    mock_system.device_type = "a3-ultra"
    mock_run_command.return_value = (1, "Error")
    self.assertFalse(
        is_GPU_TAS_possible(
            mock_system,
            CapacityType.RESERVATION,
            "cluster",
            "zone",
            "project",
        )
    )
    mock_xpk_print.assert_called_with(
        "Node pool retrieval failed, assuming TAS is not possible"
    )


if __name__ == "__main__":
  unittest.main()
