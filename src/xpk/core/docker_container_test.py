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

from unittest.mock import MagicMock
import yaml
import pytest

from .docker_container import get_main_container
from .system_characteristics import AcceleratorType, SystemCharacteristics


@pytest.fixture
def mock_args():
    """Pytest fixture for providing a mock args object."""
    args = MagicMock()
    args.use_pathways = False
    args.multi_container = False
    args.command = "echo 'hello'"
    args.debug_dump_gcs = None
    args.enable_debug_logs = False
    args.deploy_stacktrace_sidecar = False
    args.storage = []
    args.env = []
    args.docker_image = None
    args.docker_name = "test-container"
    return args


@pytest.fixture
def mock_system_characteristics():
    """Pytest fixture for providing a mock SystemCharacteristics object."""
    return SystemCharacteristics(
        topology='2x2',
        vms_per_slice=1,
        gke_accelerator='test-accelerator',
        gce_machine_type='test-machine',
        chips_per_vm=4,
        accelerator_type=AcceleratorType.TPU,
        device_type='test-device',
    )


def test_get_main_container_multi_container(
    mock_args, mock_system_characteristics
):
    """Tests that get_main_container generates correct yaml for multi-container."""
    mock_args.multi_container = True
    mock_system_characteristics.chips_per_vm = 4

    yaml_str = get_main_container(
        mock_args,
        mock_system_characteristics,
        'dummy-image',
        'google.com/tpu',
    )
    containers = yaml.safe_load(yaml_str)

    assert isinstance(containers, list)
    assert len(containers) == 2

    assert containers[0]['name'] == 'jax-tpu-1'
    assert containers[0]['image'] == 'dummy-image'
    assert containers[0]['resources']['limits']['google.com/tpu'] == 2

    assert containers[1]['name'] == 'jax-tpu-2'
    assert containers[1]['image'] == 'dummy-image'
    assert containers[1]['resources']['limits']['google.com/tpu'] == 2
