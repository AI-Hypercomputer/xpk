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

from ..utils.console import xpk_print
from .resources import ResourceManager

DEFAULT_VERTEX_TENSORBOARD_NAME = 'tb-instance'


class VertexAI:
  """Handles Vertex AI Tensorboard and Experiment creation."""

  def __init__(self, args, resource_manager: ResourceManager):
    self.args = args
    self.resource_manager = resource_manager

  def create_vertex_tensorboard(self) -> dict:
    """Creates a Tensorboard instance in Vertex AI.

    Returns:
      dict containing Tensorboard instance name, id and location.
    """
    from cloud_accelerator_diagnostics import (  # pylint: disable=import-outside-toplevel
        tensorboard,
    )

    tensorboard_name = (
        self.args.tensorboard_name
        or f'{self.args.cluster}-{DEFAULT_VERTEX_TENSORBOARD_NAME}'
    )
    instance_id = tensorboard.create_instance(  # pylint: disable=used-before-assignment
        project=self.args.project,
        location=self.args.tensorboard_region,
        tensorboard_name=self.args.tensorboard_name,
    )

    if instance_id:
      xpk_print(
          f'Tensorboard instance {tensorboard_name} is successfully created.'
      )
      return {
          'tensorboard_region': self.args.tensorboard_region,
          'tensorboard_name': tensorboard_name,
          'tensorboard_id': instance_id,
      }
    return {}

  def create_vertex_experiment(self) -> dict | None:
    """Creates an Experiment in Vertex AI.

    Returns:
      map containing Vertex Tensorboard configurations.
    """
    from cloud_accelerator_diagnostics import (  # pylint: disable=import-outside-toplevel
        tensorboard,
    )

    cluster_config_map = self.resource_manager.get_metadata_configmap()
    if (
        cluster_config_map is None
        or 'tensorboard_name' not in cluster_config_map
    ):
      xpk_print(
          'No Vertex Tensorboard instance has been created in cluster create.'
          ' Run `xpk cluster create --create-vertex-tensorboard` before running'
          ' `xpk workload create --use-vertex-tensorboard` to create a Vertex'
          ' Tensorboard instance. Alternatively, use `xpk cluster'
          ' create-pathways --create-vertex-tensorboard` before running `xpk'
          ' workload create-pathways --use-vertex-tensorboard`.'
      )
      return None

    tensorboard_config = {
        'tensorboard_project': self.args.project,
        'tensorboard_region': cluster_config_map['tensorboard_region'],
        'tensorboard_name': cluster_config_map['tensorboard_name'],
        'experiment_name': (
            self.args.experiment_name
            or f'{self.args.cluster}-{self.args.workload}'
        ),
    }

    _, tensorboard_url = tensorboard.create_experiment(
        project=self.args.project,
        location=tensorboard_config['tensorboard_region'],
        experiment_name=tensorboard_config['experiment_name'],
        tensorboard_name=tensorboard_config['tensorboard_name'],
    )

    if tensorboard_url:
      xpk_print(f'You can view Vertex Tensorboard at: {tensorboard_url}')
      return tensorboard_config

    return None
