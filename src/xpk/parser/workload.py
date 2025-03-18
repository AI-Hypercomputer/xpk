"""
Copyright 2024 Google LLC

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

from ..commands.workload import (
    workload_create,
    workload_create_pathways,
    workload_delete,
    workload_list,
)
from ..core.docker_image import DEFAULT_DOCKER_IMAGE, DEFAULT_SCRIPT_DIR
from .common import add_shared_arguments
from .validators import directory_path_type, name_type


def set_workload_parsers(workload_parser):
  workload_subcommands = workload_parser.add_subparsers(
      title='workload subcommands',
      dest='xpk_workload_subcommands',
      help=(
          '`create`, `create-pathways`, `list` and `delete` workloads on'
          ' clusters'
      ),
  )

  # "workload create" command parser.
  workload_create_parser = workload_subcommands.add_parser(
      'create', help='Create a new job.'
  )
  workload_create_parser_required_arguments = (
      workload_create_parser.add_argument_group(
          'Workload Built-in Arguments',
          'Configure xpk to create a Workload for you.',
      )
  )
  workload_create_parser_optional_arguments = (
      workload_create_parser.add_argument_group(
          'Optional Arguments', 'Arguments optional for `workload create`.'
      )
  )
  workload_base_docker_image_arguments = workload_create_parser.add_argument_group(
      'Base Docker Image Arguments',
      'User supplies a base image or by default the image is set by xpk.'
      ' Xpk will add the `script_dir` to the base image creating an anonymous'
      ' docker image. These arguments are exclusive to `--docker-image`.',
  )
  workload_docker_image_arguments = workload_create_parser.add_argument_group(
      'Docker Image Arguments',
      '`--base-docker-image` is used by default. Set this argument if the'
      ' user wants the docker image to be used directly by the xpk workload.',
  )
  workload_create_autoprovisioning_arguments = (
      workload_create_parser.add_argument_group(
          'Optional Autoprovisioning Arguments',
          'Arguments for configuring autoprovisioning.',
      )
  )

  workload_vertex_tensorboard_arguments = (
      workload_create_parser.add_argument_group(
          'Vertex Tensorboard Arguments',
          'Arguments for creating Vertex AI Experiment in workload create.',
      )
  )

  ### "workload create" Required arguments
  workload_create_parser_required_arguments.add_argument(
      '--command',
      type=str,
      default=None,
      help=(
          'Main command to run on each VM. This script runs within the docker'
          ' container. Typically this looks like "--command=\'python3'
          ' train.py\'" but if your docker container is missing the'
          ' dependencies, it might look more like "--command=\'bash setup.sh &&'
          ' python3 train.py\'".'
      ),
      required=True,
  )
  workload_device_group = (
      workload_create_parser_required_arguments.add_mutually_exclusive_group(
          required=True
      )
  )
  workload_device_group.add_argument(
      '--tpu-type',
      type=str,
      default=None,
      help='The tpu type to use, v5litepod-16, etc.',
  )
  workload_device_group.add_argument(
      '--device-type',
      type=str,
      default=None,
      help=(
          'The device type to use (can be tpu or gpu or cpu), v5litepod-16,'
          ' h100-80gb-8, n2-standard-32-4 etc.'
      ),
  )

  workload_create_parser_optional_arguments.add_argument(
      '--storage',
      action='append',
      default=[],
      help='Names of storages the workload uses',
  )
  workload_create_parser_optional_arguments.add_argument(
      '--num-nodes',
      type=int,
      default=1,
      help='The number of nodes to use, default=1.',
  )
  workload_create_parser_optional_arguments.add_argument(
      '--scheduler',
      type=str,
      default='default-scheduler',
      help=(
          'Which scheduler you want to use. Defaults to `default-scheduler`. If'
          ' your cluster is configured for high throughput scheduling, you'
          ' might want to use `gke.io/high-throughput-scheduler`.If your'
          ' cluster is configured for topology-aware scheduling, you might want'
          ' to use `gke.io/topology-aware-auto`.'
      ),
  )
  workload_create_parser_optional_arguments.add_argument(
      '--debug-dump-gcs',
      type=str,
      default=None,
      help=(
          'GCS bucket or a directory within a bucket, e.g gs://bucket/subdir, '
          'where debugging information such as HLO dumps are uploaded'
      ),
  )
  workload_create_parser_optional_arguments.add_argument(
      '--deploy-stacktrace-sidecar',
      action='store_true',
      help=(
          'Add this argument to deploy a sidecar container that will '
          'read the stack traces collected in /tmp/debugging directory '
          'and forward them to Cloud Logging for TPU workloads.'
      ),
  )

  workload_create_parser_optional_arguments.add_argument(
      '--use-pathways',
      action='store_true',
      help=(
          'Please use `xpk workload create-pathways` instead to'
          ' create Pathways workloads.'
      ),
  )

  # Autoprovisioning workload arguments
  workload_create_autoprovisioning_arguments.add_argument(
      '--on-demand',
      action='store_true',
      help=(
          'Sets autoprovisioning to use on-demand resources for the workload'
          ' request. See `--reservation` or `--spot` for other capacity types.'
      ),
  )
  workload_create_autoprovisioning_arguments.add_argument(
      '--reservation',
      type=str,
      help=(
          'Sets autoprovisioning to use reservation resources for the workload'
          ' request. This will attempt to find the provided reservation. See'
          ' `--spot` or `--on-demand` for other capacity types.'
      ),
  )
  workload_create_autoprovisioning_arguments.add_argument(
      '--spot',
      action='store_true',
      help=(
          'Sets autoprovisioning to use spot resources.'
          ' See `--reservation` or `--on-demand` for other capacity types.'
      ),
  )

  # "workload create-pathways" command parser.
  workload_create_pathways_parser = workload_subcommands.add_parser(
      'create-pathways', help='Create a new job.'
  )
  workload_create_pathways_parser_required_arguments = (
      workload_create_pathways_parser.add_argument_group(
          'Workload create-pathways Built-in Arguments',
          'Configure xpk to create a Pathways Workload for you.',
      )
  )
  workload_create_pathways_parser_optional_arguments = (
      workload_create_pathways_parser.add_argument_group(
          'Optional Arguments',
          'Arguments optional for `workload create-pathways`.',
      )
  )
  workload_create_pathways_base_docker_image_arguments = workload_create_pathways_parser.add_argument_group(
      'Base Docker Image Arguments',
      'User supplies a base image or by default the image is set by xpk.'
      ' Xpk will add the `script_dir` to the base image creating an anonymous'
      ' docker image. These arguments are exclusive to `--docker-image`.',
  )
  workload_create_pathways_docker_image_arguments = workload_create_pathways_parser.add_argument_group(
      'Docker Image Arguments',
      '`--base-docker-image` is used by default. Set this argument if the'
      ' user wants the docker image to be used directly by the xpk workload.',
  )
  workload_create_pathways_vertex_tensorboard_arguments = (
      workload_create_pathways_parser.add_argument_group(
          'Vertex Tensorboard Arguments',
          'Arguments for creating Vertex AI Experiment in workload create.',
      )
  )

  ### "workload create-pathways" Required arguments, specific to Pathways
  workload_create_pathways_parser_required_arguments.add_argument(
      '--tpu-type',
      type=str,
      default=None,
      help='The tpu type to use, v5litepod-16, etc.',
  )

  ### "workload create-pathways" Optional arguments, specific to Pathways
  workload_create_pathways_parser_optional_arguments.add_argument(
      '--headless',
      action='store_true',
      help=(
          'Please provide this argument to create Pathways workloads in'
          ' headless mode. This arg can only be used in `xpk workload'
          ' create-pathways`.'
      ),
  )
  workload_create_pathways_parser_optional_arguments.add_argument(
      '--proxy-server-image',
      type=str,
      default=(
          'us-docker.pkg.dev/cloud-tpu-v2-images/pathways/proxy_server:latest'
      ),
      help=(
          'Please provide the proxy server image for Pathways. This arg can'
          ' only be used in `xpk workload create-pathways`.'
      ),
  )
  workload_create_pathways_parser_optional_arguments.add_argument(
      '--server-image',
      type=str,
      default='us-docker.pkg.dev/cloud-tpu-v2-images/pathways/server:latest',
      help=(
          'Please provide the server image for Pathways. This arg can only be'
          ' used in `xpk workload create-pathways`.'
      ),
  )
  workload_create_pathways_parser_optional_arguments.add_argument(
      '--pathways-gcs-location',
      type=str,
      default='gs://cloud-pathways-staging/tmp',
      help=(
          'Please provide the GCS location to store Pathways artifacts. This'
          ' arg can only be used in `xpk workload create-pathways`.'
      ),
  )
  workload_create_pathways_parser_optional_arguments.add_argument(
      '--command',
      type=str,
      default=None,
      help=(
          'Main command to run on each VM. This script runs within the docker'
          ' container. Typically this looks like "--command=\'python3'
          ' train.py\'" but if your docker container is missing the'
          ' dependencies, it might look more like "--command=\'bash setup.sh &&'
          ' python3 train.py\'".'
      ),
      required=False,
  )
  workload_create_pathways_parser_optional_arguments.add_argument(
      '--storage',
      action='append',
      default=[],
      help='Names of storages the workload uses',
  )

  workload_create_pathways_parser_optional_arguments.add_argument(
      '--custom-pathways-server-args',
      type=str,
      default=None,
      help=(
          'Provide custom Pathways server args as follows -'
          " --custom-pathways-server-args='--arg_1=xxx --arg2=yyy'"
      ),
      required=False,
  )

  workload_create_pathways_parser_optional_arguments.add_argument(
      '--custom-pathways-proxy-server-args',
      type=str,
      default=None,
      help=(
          'Provide custom Pathways proxy server args as follows -'
          " --custom-pathways-proxy-server-args='--arg_1=xxx --arg2=yyy'"
      ),
      required=False,
  )

  workload_create_pathways_parser_optional_arguments.add_argument(
      '--custom-pathways-worker-args',
      type=str,
      default=None,
      help=(
          'Provide custom Pathways worker args as follows -'
          " --custom-pathways-worker-args='--arg_1=xxx --arg2=yyy'"
      ),
      required=False,
  )

  add_shared_workload_create_required_arguments([
      workload_create_parser_required_arguments,
      workload_create_pathways_parser_required_arguments,
  ])
  add_shared_workload_create_optional_arguments([
      workload_create_parser_optional_arguments,
      workload_create_pathways_parser_optional_arguments,
  ])
  add_shared_workload_create_env_arguments([
      workload_create_parser_optional_arguments,
      workload_create_pathways_parser_optional_arguments,
  ])
  add_shared_workload_base_docker_image_arguments([
      workload_base_docker_image_arguments,
      workload_create_pathways_base_docker_image_arguments,
  ])
  add_shared_workload_docker_image_arguments([
      workload_docker_image_arguments,
      workload_create_pathways_docker_image_arguments,
  ])
  add_shared_workload_create_tensorboard_arguments([
      workload_vertex_tensorboard_arguments,
      workload_create_pathways_vertex_tensorboard_arguments,
  ])

  # Set defaults for both workload create and workload create-pathways after adding all shared args.
  workload_create_parser.set_defaults(func=workload_create)
  workload_create_pathways_parser.set_defaults(func=workload_create_pathways)

  # "workload delete" command parser.
  workload_delete_parser = workload_subcommands.add_parser(
      'delete', help='Delete job.'
  )
  workload_delete_parser_required_arguments = (
      workload_delete_parser.add_argument_group(
          'Required Arguments',
          'Arguments required for `job delete`.',
      )
  )
  workload_delete_parser_optional_arguments = (
      workload_delete_parser.add_argument_group(
          'Optional Arguments', 'Arguments optional for `job delete`.'
      )
  )
  add_shared_arguments(workload_delete_parser_optional_arguments)

  ### "workload delete" Required arguments
  workload_delete_parser_required_arguments.add_argument(
      '--cluster',
      type=name_type,
      default=None,
      help='The name of the cluster to delete the job on.',
      required=True,
  )
  ### "workload delete" Optional arguments
  workload_delete_parser_optional_arguments.add_argument(
      '--workload',
      type=name_type,
      default=None,
      help=(
          'The name of the workload to delete. If the workload is not'
          ' specified, all workloads will be deleted from the cluster.'
      ),
  )
  workload_delete_parser_optional_arguments.add_argument(
      '--filter-by-job',
      type=str,
      help=(
          'Filters the arguments based on job name. Provide a regex'
          ' expressionto parse jobs that match the pattern or provide a job'
          ' name to delete a single job.'
      ),
  )
  workload_delete_parser_optional_arguments.add_argument(
      '--filter-by-status',
      type=str,
      default='EVERYTHING',
      choices=[
          'EVERYTHING',
          'FINISHED',
          'RUNNING',
          'QUEUED',
          'FAILED',
          'SUCCESSFUL',
      ],
      help=(
          'Filters the arguments based on status. Selected filters are listed'
          ' above. FAILED and SUCCESSFUL are sub-states of FINISHED.'
      ),
      required=False,
  )
  workload_delete_parser_optional_arguments.add_argument(
      '--force',
      action='store_true',
      help=(
          'Forces workload deletion command to run without additional approval.'
      ),
  )

  workload_delete_parser.set_defaults(func=workload_delete)

  # "workload list" command parser.
  workload_list_parser = workload_subcommands.add_parser(
      'list', help='List jobs.'
  )

  workload_list_parser.add_argument(
      '--cluster',
      type=name_type,
      default=None,
      help='The name of the cluster to list jobs on.',
      required=True,
  )

  workload_list_parser.add_argument(
      '--filter-by-status',
      type=str,
      default='EVERYTHING',
      choices=[
          'EVERYTHING',
          'FINISHED',
          'RUNNING',
          'QUEUED',
          'FAILED',
          'SUCCESSFUL',
      ],
      help=(
          'Filters the arguments based on status. Selected filters are listed'
          ' above. FAILED and SUCCESSFUL are sub-states of FINISHED.'
      ),
      required=False,
  )

  workload_list_parser.add_argument(
      '--filter-by-job',
      type=str,
      help=(
          'Filters the arguments based on job name. Provide a regex'
          ' expressionto parse jobs that match the pattern or provide a job'
          ' name to view a single job.'
      ),
      required=False,
  )

  workload_list_wait_for_job_completion_arguments = (
      workload_list_parser.add_argument_group(
          'Wait for Job Completion Arguments',
          'Arguments for waiting on the completion of a job.',
      )
  )

  workload_list_wait_for_job_completion_arguments.add_argument(
      '--wait-for-job-completion',
      type=str,
      default=None,
      help='The name of the job to wait on.',
      required=False,
  )

  workload_list_wait_for_job_completion_arguments.add_argument(
      '--timeout',
      type=int,
      default=None,
      help=(
          'Amount of time to wait for job in seconds. Default is the max wait'
          ' time, 1 week.'
      ),
      required=False,
  )

  add_shared_arguments(workload_list_parser)

  workload_list_parser.set_defaults(func=workload_list)


def add_shared_workload_create_required_arguments(args_parsers):
  """Add shared required arguments in workload create and Pathways workload create.

  Args:
      List of workload create required arguments parsers
  """
  for custom_parser in args_parsers:
    custom_parser.add_argument(
        '--workload',
        type=name_type,
        default=None,
        help='The name of the workload to run.',
        required=True,
    )
    custom_parser.add_argument(
        '--cluster',
        type=name_type,
        default=None,
        help='The name of the cluster to run the job on.',
        required=True,
    )


def add_shared_workload_create_optional_arguments(args_parsers):
  """Add shared optional arguments in workload create and Pathways workload create.

  Args:
      List of workload create optional arguments parsers
  """
  for custom_parser in args_parsers:
    add_shared_arguments(custom_parser)
    custom_parser.add_argument(
        '--docker-name',
        type=str,
        default='jax-tpu',
        help=(
            'The name of the docker-image to use, default and typically'
            ' `jax-tpu`.'
        ),
    )
    custom_parser.add_argument(
        '--num-slices',
        type=int,
        default=1,
        help='The number of slices to use, default=1.',
    )
    custom_parser.add_argument(
        '--priority',
        type=str,
        default='medium',
        choices=['very-low', 'low', 'medium', 'high', 'very-high'],
        help=(
            'A priority, one of `very-low`, `low`, `medium`, `high` or'
            ' `very-high`. Defaults to `medium`.'
        ),
    )
    custom_parser.add_argument(
        '--max-restarts',
        type=str,
        default='0',
        help=(
            'Maximum number of times the JobSet will be restarted upon failure.'
            ' Defaults to 0.'
        ),
    )
    custom_parser.add_argument(
        '--ttl-seconds-after-finished',
        type=int,
        default=12 * 60 * 60,
        help=(
            'Set the number of seconds to clean up finished Jobsets (either'
            ' Complete or Failed). This is by default set to 12 hours.'
        ),
    )
    custom_parser.add_argument(
        '-tgps',
        '--termination-grace-period-seconds',
        type=str,
        default='30',
        help=(
            'Maximum wait time for a workload Pod to wrap up after a disruption'
            ' event or deletion request.Defaults to 30 seconds.'
        ),
    )
    custom_parser.add_argument(
        '--remote-python-sidecar-image',
        type=str,
        default=None,
        help='Remote Python sidecar server image.',
    )
    custom_parser.add_argument(
        '--enable-debug-logs',
        action='store_true',
        help=(
            'Set this flag to get verbose logging to investigate the issue in'
            ' the workload.'
        ),
    )
    custom_parser.add_argument(
        '--restart-on-exit-codes',
        type=str,
        default=None,
        help=(
            'Adding this argument specifies additional user-defined exit codes'
            ' that allow restarting the workload when --max-restarts is set to'
            ' a value greater than 0. By default, workloads restart on exit'
            ' codes 42 and 127-255. Any exit codes provided through this flag'
            ' will be included alongside the default codes for restarting'
            ' conditions.'
        ),
    )
    custom_parser.add_argument(
        '--ramdisk-directory',
        type=str,
        default='',
        help=(
            'The directory of the locally mounted RAM disk. This is only to'
            ' be used with the CSI driver provided by GKE.'
        ),
    )


def add_shared_workload_create_env_arguments(args_parsers):
  """Add shared workload create environment arguments in workload create and Pathways workload create.

  Args:
      List of workload create environment arguments parsers
  """
  for custom_parser in args_parsers:
    workload_env_arguments = custom_parser.add_mutually_exclusive_group()
    workload_env_arguments.add_argument(
        '--env-file',
        type=str,
        default=None,
        help=(
            'Environment file to be applied to the container.  This file should'
            ' use the syntax <variable>=value (which sets the variable to the'
            ' given value) or <variable> (which takes the value from the local'
            ' environment), and # for comments.'
        ),
    )
    workload_env_arguments.add_argument(
        '--env',
        action='append',
        type=str,
        help=(
            'Environment variable to set in the container environment. '
            'The format is <variable>=value'
        ),
    )


def add_shared_workload_base_docker_image_arguments(args_parsers):
  """Add shared base docker image arguments in workload create and Pathways workload create.

  Args:
      List of workload create base docker image arguments parsers
  """
  for custom_parser in args_parsers:
    custom_parser.add_argument(
        '--base-docker-image',
        type=str,
        default=DEFAULT_DOCKER_IMAGE,
        help=(
            'The base docker-image to use, default'
            f' {DEFAULT_DOCKER_IMAGE}. If using a custom docker image it'
            ' is typically addressed as gcr.io/${PROJECT}/${NAME}:latest.'
            ' This docker image will be used as a base image by default and'
            ' the `--script-dir` by default will be added to the image.'
        ),
    )
    custom_parser.add_argument(
        '--script-dir',
        type=directory_path_type,
        default=DEFAULT_SCRIPT_DIR,
        help=(
            'The local location of the directory to copy to the docker image'
            ' and run the main command from. Defaults to current working'
            ' directory.'
        ),
    )


def add_shared_workload_docker_image_arguments(args_parsers):
  """Add shared docker image arguments in workload create and Pathways workload create.

  Args:
      List of workload create docker image arguments parsers
  """
  for custom_parser in args_parsers:
    custom_parser.add_argument(
        '--docker-image',
        type=str,
        help=(
            'The version of the docker-image to use. By default, '
            ' `--base-docker-image` is used. Set this argument if the user'
            ' wants the docker image to be used directly by the xpk workload. a'
            ' custom docker image it is typically addressed as'
            ' gcr.io/${PROJECT}/${NAME}:latest. This docker image will be used'
            ' directly by the xpk workload.'
        ),
    )


def add_shared_workload_create_tensorboard_arguments(args_parsers):
  """Add shared tensorboard arguments in workload create and Pathways workload create.

  Args:
      List of workload create optional arguments parsers
  """
  for custom_parser in args_parsers:
    custom_parser.add_argument(
        '--use-vertex-tensorboard',
        action='store_true',
        help='Set this flag to view workload data on Vertex Tensorboard.',
    )
    custom_parser.add_argument(
        '--experiment-name',
        type=str,
        required=False,
        help=(
            'The name of Vertex Experiment to create. '
            'If not specified, a Vertex Experiment with the name '
            '<cluster>-<workload> will be created.'
        ),
    )
