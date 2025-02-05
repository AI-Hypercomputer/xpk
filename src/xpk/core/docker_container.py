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

from ..utils.console import xpk_exit, xpk_print
from .docker_image import setup_docker_image
from .docker_resources import (
    add_container_ports,
    add_image_pull_policy_for_pw_or_gpu,
    add_jax_coordinator_port,
    get_env_container,
    get_main_container_resources,
    get_volume_mounts,
)
from .monitoring import get_gke_debugging_dashboard
from .system_characteristics import (
    AcceleratorType,
    AcceleratorTypeToAcceleratorCharacteristics,
    SystemCharacteristics,
)


def get_main_and_sidecar_container(args, system, docker_image) -> str:
  """Generate yaml for main and sidecar container.
  Args:
    args: user provided arguments for running the command.
    system: system characteristics
    docker_image: docker image

  Returns:
    str:
      yaml for main and sidecar container
  """
  resource_type = AcceleratorTypeToAcceleratorCharacteristics[
      system.accelerator_type
  ].resource_type
  main_container = get_main_container(args, system, docker_image, resource_type)
  yaml = """- name: stacktrace-explorer
                image: busybox:1.28
                args: [/bin/sh, -c, "check_signal() (while [ ! -f /shared-volume/stacktrace_signal ]; do sleep 1; done; pid=$(pidof 'tail'); kill $pid;); check_signal & while [ ! -d /tmp/debugging ]; do sleep 60; done; while [ ! -e /tmp/debugging/* ]; do sleep 60; done; tail -n+1 -f /tmp/debugging/*; exit 0;"]
                volumeMounts:
                - name: tpu-stack-trace
                  readOnly: true
                  mountPath: /tmp/debugging
                - name: shared-data
                  mountPath: /shared-volume
              {main_container}
  """
  return yaml.format(main_container=main_container)


def get_main_container(args, system, docker_image, resource_type) -> str:
  """Generate yaml for main container including the xpk command.
  Args:
    args: user provided arguments for running the command.
    system: system characteristics
    docker_image: docker image
    resource_type: The label to describe the resource type for TPUs/GPUs/CPUs.

  Returns:
    str:
      yaml for main container
  """

  xpk_internal_commands = ''
  gsutil_test_command = ''
  if not args.use_pathways and args.debug_dump_gcs:
    gsutil_test_command = (
        'which gsutil >/dev/null 2>&1 || { echo >&2 "gsutil'
        ' is required but not installed. Aborting"; exit 24;};'
    )
    xpk_internal_commands += (
        'WORKER_ID=$HOSTNAME;'
        f'gsutil -m cp -r /tmp/xla_dump/ {args.debug_dump_gcs}/$WORKER_ID;'
    )

  command = args.command
  if args.enable_debug_logs:
    command = (
        'export TPU_STDERR_LOG_LEVEL=0 &&'
        ' export TPU_MIN_LOG_LEVEL=0 &&'
        ' export TF_CPP_MIN_LOG_LEVEL=0 &&'
        ' export TPU_VMODULE=real_program_continuator=1 &&'
        f' {args.command}'
    )

  gpu_workload_terminate_command = ''
  if system.accelerator_type == AcceleratorType['GPU']:
    gpu_workload_terminate_command = (
        'echo Main app is done > /usr/share/workload/workload_terminated; '
    )

  tpu_stacktrace_terminate_command = ''
  if (
      not args.use_pathways
      and system.accelerator_type == AcceleratorType['TPU']
      and args.deploy_stacktrace_sidecar
  ):
    tpu_stacktrace_terminate_command = (
        'touch /shared-volume/stacktrace_signal; '
    )

  yaml = """- name: {docker_name}
                image: {docker_image}
                {image_pull_policy}
                env: {env}
                ports:
                {container_ports}
                {jax_coordinator_port}
                securityContext:
                  privileged: true
                command:
                - bash
                - -c
                - |
                  echo XPK Start: $(date);
                  _sigterm() (kill -SIGTERM $! 2>/dev/null;);
                  trap _sigterm SIGTERM;
                  {gsutil_test_command}
                  ({command}) & PID=$!;
                  while kill -0 $PID 2>/dev/null;
                      do sleep 5;
                  done;
                  wait $PID;
                  EXIT_CODE=$?;
                  {xpk_internal_commands}
                  echo XPK End: $(date);
                  echo EXIT_CODE=$EXIT_CODE;
                  {tpu_stacktrace_terminate_command}
                  {gpu_workload_terminate_command}
                  exit $EXIT_CODE
                resources:
                  limits:
                    {resources}
"""
  volume_mounts = get_volume_mounts(args, system)
  if volume_mounts != '':
    yaml += """
                volumeMounts:
                {volume_mounts}
"""
  return yaml.format(
      args=args,
      system=system,
      image_pull_policy=add_image_pull_policy_for_pw_or_gpu(args, system),
      env=get_env_container(args, system),
      container_ports=add_container_ports(args, system),
      jax_coordinator_port=add_jax_coordinator_port(system),
      docker_name=get_main_container_docker_image(args, system),
      docker_image=docker_image,
      gsutil_test_command=gsutil_test_command,
      command=command,
      tpu_stacktrace_terminate_command=tpu_stacktrace_terminate_command,
      gpu_workload_terminate_command=gpu_workload_terminate_command,
      xpk_internal_commands=xpk_internal_commands,
      resources=get_main_container_resources(args, system, resource_type),
      volume_mounts=volume_mounts,
  )


def get_user_workload_container(args, system: SystemCharacteristics):
  """Deploy user workload container

  Args:
      args: user provided args.
      system: system characteristics.

  Returns:
      container: main container
      debugging_dashboard_id: id of the GKE dashboard
  """

  setup_docker_image_code, docker_image = setup_docker_image(args)
  if setup_docker_image_code != 0:
    xpk_exit(setup_docker_image_code)

  # Determine if we deploy a sidecar and if we deploy a container.
  debugging_dashboard_id = None
  resource_type = AcceleratorTypeToAcceleratorCharacteristics[
      system.accelerator_type
  ].resource_type
  if (
      not args.use_pathways
      and system.accelerator_type == AcceleratorType['TPU']
      and args.deploy_stacktrace_sidecar
  ):
    xpk_print(
        'Sidecar container to display stack traces for TPU workloads will also'
        ' be deployed.'
    )
    container = get_main_and_sidecar_container(args, system, docker_image)
    # Get GKE debugging dashboard only when sidecar container is deployed for TPU workloads
    debugging_dashboard_id = get_gke_debugging_dashboard(args)
  else:
    container = get_main_container(args, system, docker_image, resource_type)
  return container, debugging_dashboard_id


def get_main_container_docker_image(args, system: SystemCharacteristics) -> str:
  """Docker name for the main container.
  Args:
    args: user provided args.
    system: system characteristics.

  Returns:
    str:
      Workload docker image as a YAML string
  """

  if system.accelerator_type == AcceleratorType['GPU']:
    return 'gpu-image'

  return f'{args.docker_name}'
