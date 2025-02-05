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
from .resources import CLUSTER_METADATA_CONFIGMAP, get_cluster_configmap

DEFAULT_VERTEX_TENSORBOARD_NAME = 'tb-instance'


def create_vertex_tensorboard(args) -> dict:
  """Creates a Tensorboard instance in Vertex AI.

  Args:
    args: user provided arguments.

  Returns:
    dict containing Tensorboard instance name, id and location.
  """
  from cloud_accelerator_diagnostics import (  # pylint: disable=import-outside-toplevel
      tensorboard,
  )

  tensorboard_config = {}
  tensorboard_name = args.tensorboard_name
  if tensorboard_name is None:
    tensorboard_name = f'{args.cluster}-{DEFAULT_VERTEX_TENSORBOARD_NAME}'
  instance_id = tensorboard.create_instance(  # pylint: disable=used-before-assignment
      project=args.project,
      location=args.tensorboard_region,
      tensorboard_name=tensorboard_name,
  )
  if instance_id:
    xpk_print(
        f'Tensorboard instance {tensorboard_name} is successfully created.'
    )
    tensorboard_config['tensorboard_region'] = args.tensorboard_region
    tensorboard_config['tensorboard_name'] = tensorboard_name
    tensorboard_config['tensorboard_id'] = instance_id
  return tensorboard_config


def create_vertex_experiment(args) -> dict | None:
  """Creates an Experiment in Vertex AI.

  Args:
    args: user provided arguments.

  Returns:
    map containing Vertex Tensorboard configurations.
  """
  from cloud_accelerator_diagnostics import (  # pylint: disable=import-outside-toplevel
      tensorboard,
  )

  metadata_configmap_name = f'{args.cluster}-{CLUSTER_METADATA_CONFIGMAP}'
  cluster_config_map = get_cluster_configmap(args, metadata_configmap_name)

  if cluster_config_map is None or 'tensorboard_name' not in cluster_config_map:
    xpk_print(
        'No Vertex Tensorboard instance has been created in cluster create. Run'
        ' `xpk cluster create --create-vertex-tensorboard` before running `xpk'
        ' workload create --use-vertex-tensorboard` to create a Vertex'
        ' Tensorboard instance. Alternatively, use `xpk cluster create-pathways'
        ' --create-vertex-tensorboard` before running `xpk workload'
        ' create-pathways --use-vertex-tensorboard`.'
    )
    return None

  tensorboard_config = {}
  tensorboard_config['tensorboard_project'] = args.project
  tensorboard_config['tensorboard_region'] = cluster_config_map[
      'tensorboard_region'
  ]
  tensorboard_config['tensorboard_name'] = cluster_config_map[
      'tensorboard_name'
  ]
  experiment_name = args.experiment_name
  if experiment_name is None:
    experiment_name = f'{args.cluster}-{args.workload}'
  tensorboard_config['experiment_name'] = experiment_name

  _, tensorboard_url = tensorboard.create_experiment(
      project=args.project,
      location=tensorboard_config['tensorboard_region'],
      experiment_name=experiment_name,
      tensorboard_name=tensorboard_config['tensorboard_name'],
  )
  if tensorboard_url is None:
    return None

  xpk_print(f'You can view Vertex Tensorboard at: {tensorboard_url}')
  return tensorboard_config
