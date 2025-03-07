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
from .cluster import ClusterManager
from .docker_image import DockerImageManager
from .docker_resources import ContainerResources
from .monitoring import GKEDashboardManager
from .system_characteristics import (
    AcceleratorType,
    AcceleratorTypeToAcceleratorCharacteristics,
    SystemCharacteristics,
)


class ContainerConfig:
  """
  Manages container deployment, including generation of YAML configurations
  for main and sidecar containers, managing Docker images, and handling TPU/GPU/CPU workloads.
  """

  def __init__(
      self,
      args,
      system: SystemCharacteristics,
      docker_image_manager: DockerImageManager,
      container_resources: ContainerResources,
      gke_dashboard_manager: GKEDashboardManager,
      cluster_manager: ClusterManager,
  ):
    self.args = args
    self.system = system
    self.docker_image_manager = docker_image_manager
    self.container_config = container_resources
    self.gke_dashboard_manager = gke_dashboard_manager
    self.cluster_manager = cluster_manager

  def get_main_and_sidecar_container(self, docker_image) -> str:
    """Generate yaml for main and sidecar container.
    Args:
      docker_image: docker image

    Returns:
      str:
        yaml for main and sidecar container
    """
    resource_type = AcceleratorTypeToAcceleratorCharacteristics[
        self.system.accelerator_type
    ].resource_type
    main_container = self.get_main_container(docker_image, resource_type)
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

  def get_main_container(self, docker_image, resource_type) -> str:
    """Generate yaml for main container including the xpk command.
    Args:
      docker_image: docker image
      resource_type: The label to describe the resource type for TPUs/GPUs/CPUs.

    Returns:
      str:
        yaml for main container
    """
    xpk_internal_commands = ''
    gsutil_test_command = ''
    if not self.args.use_pathways and self.args.debug_dump_gcs:
      gsutil_test_command = (
          'which gsutil >/dev/null 2>&1 || { echo >&2 "gsutil'
          ' is required but not installed. Aborting"; exit 24;};'
      )
      xpk_internal_commands += (
          'WORKER_ID=$HOSTNAME;gsutil -m cp -r /tmp/xla_dump/'
          f' {self.args.debug_dump_gcs}/$WORKER_ID;'
      )

    command = self.args.command
    if self.args.enable_debug_logs:
      command = (
          'export TPU_STDERR_LOG_LEVEL=0 &&'
          ' export TPU_MIN_LOG_LEVEL=0 &&'
          ' export TF_CPP_MIN_LOG_LEVEL=0 &&'
          ' export TPU_VMODULE=real_program_continuator=1 &&'
          f' {self.args.command}'
      )

    gpu_workload_terminate_command = ''
    if self.system.accelerator_type == AcceleratorType['GPU']:
      gpu_workload_terminate_command = (
          'echo Main app is done > /usr/share/workload/workload_terminated; '
      )

    tpu_stacktrace_terminate_command = ''
    if (
        not self.args.use_pathways
        and self.system.accelerator_type == AcceleratorType['TPU']
        and self.args.deploy_stacktrace_sidecar
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
    container_config = ContainerResources(
        self.args, self.system, self.cluster_manager
    )
    volume_mounts = container_config.get_volume_mounts()
    if volume_mounts != '':
      yaml += """
                volumeMounts:
                {volume_mounts}
  """
    return yaml.format(
        args=self.args,
        system=self.system,
        image_pull_policy=container_config.add_image_pull_policy_for_pw_or_gpu(),
        env=container_config.get_env_container(),
        container_ports=container_config.add_container_ports(),
        jax_coordinator_port=container_config.add_jax_coordinator_port(),
        docker_name=self.get_main_container_docker_image(),
        docker_image=docker_image,
        gsutil_test_command=gsutil_test_command,
        command=command,
        tpu_stacktrace_terminate_command=tpu_stacktrace_terminate_command,
        gpu_workload_terminate_command=gpu_workload_terminate_command,
        xpk_internal_commands=xpk_internal_commands,
        resources=container_config.get_main_container_resources(resource_type),
        volume_mounts=volume_mounts,
    )

  def get_user_workload_container(self):
    """Deploy user workload container

    Returns:
        container: main container
        debugging_dashboard_id: id of the GKE dashboard
    """
    setup_docker_image_code, docker_image = (
        self.docker_image_manager.setup_docker_image()
    )
    if setup_docker_image_code != 0:
      xpk_exit(setup_docker_image_code)

    # Determine if we deploy a sidecar and if we deploy a container.
    debugging_dashboard_id = None
    resource_type = AcceleratorTypeToAcceleratorCharacteristics[
        self.system.accelerator_type
    ].resource_type
    if (
        not self.args.use_pathways
        and self.system.accelerator_type == AcceleratorType['TPU']
        and self.args.deploy_stacktrace_sidecar
    ):
      xpk_print(
          'Sidecar container to display stack traces for TPU workloads will'
          ' also be deployed.'
      )
      container = self.get_main_and_sidecar_container(docker_image)
      # Get GKE debugging dashboard only when sidecar container is deployed for TPU workloads
      debugging_dashboard_id = (
          self.gke_dashboard_manager.get_debugging_dashboard()
      )
    else:
      container = self.get_main_container(docker_image, resource_type)
    return container, debugging_dashboard_id

  def get_main_container_docker_image(self) -> str:
    """Docker name for the main container.

    Returns:
      str:
        Workload docker image as a YAML string
    """

    if self.system.accelerator_type == AcceleratorType['GPU']:
      return 'gpu-image'

    return f'{self.args.docker_name}'
