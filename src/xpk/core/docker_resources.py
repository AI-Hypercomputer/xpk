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

import os
import re
from .cluster import setup_k8s_env
from .storage import GCS_FUSE_TYPE, GCP_FILESTORE_TYPE, PARALLELSTORE_TYPE, GCE_PD_TYPE, LUSTRE_TYPE, Storage, get_storages_to_mount
from .system_characteristics import AcceleratorType, SystemCharacteristics
from ..utils.execution_context import is_dry_run


def get_main_container_resources(
    args, system: SystemCharacteristics, resource_type
) -> str:
  """Resources for the main container.
  Args:
    args: user provided args.
    system: system characteristics.
    resource_type: TPU / GPU / CPU

  Returns:
    str:
      Workload resources port as a YAML string
  """
  # Resources requirements for Pathways workload containers are known.
  resources_yaml = """cpu: "24"
                    memory: 100G"""
  if args.use_pathways:
    return resources_yaml

  gpu_resources_yaml = """nvidia.com/gpu: {system.chips_per_vm}"""
  if system.accelerator_type == AcceleratorType.GPU:
    return gpu_resources_yaml.format(system=system)

  if system.accelerator_type == AcceleratorType.CPU:
    # CPUs don't have chips, but have a subresource called vCPUs.
    # system.chips_per_vm is used as a proxy for vCPUs.
    # Some vCPUs get used in hosting system pods of the workloads,
    # hence an offset of 0.95 is introduced.
    offset_vCPUs = int(system.chips_per_vm) * 0.95
    return f'{resource_type}: {offset_vCPUs}'

  return (
      f'{resource_type}:'
      f' {int(system.chips_per_vm / system.parallel_containers)}'
  )


def get_env_container(args, system: SystemCharacteristics) -> str:
  """Environment configuration for the main container.
  Args:
    args: user provided args.
    system: system characteristics.

  Returns:
    str:
      YAML with the env config for the main container, as a YAML string.
  """
  if system.accelerator_type == AcceleratorType.GPU:
    return get_gpu_env(args, system)

  if system.accelerator_type == AcceleratorType.CPU:
    return get_cpu_env(args, system)

  return format_env_dict(args.env, system)


def get_gpu_env(args, system) -> str:
  """Generate environment variables for GPU nodepools
  Args:
    num_slices: Number of slices to be used in the workload.
    env_vars: Environment variables, processed from user args.
    system: system characteristics

  Returns:
    str: yaml containing env variables
  """
  gpu_env_yaml = """
                  - name: REPLICATED_JOB_NAME
                    valueFrom:
                      fieldRef:
                        fieldPath: metadata.annotations['jobset.sigs.k8s.io/replicatedjob-name']
                  - name: JOBSET_NAME
                    valueFrom:
                      fieldRef:
                        fieldPath: metadata.annotations['jobset.sigs.k8s.io/jobset-name']
                  - name: NNODES
                    value: "{args.num_nodes}"
                  - name: NODE_RANK
                    valueFrom:
                      fieldRef:
                        fieldPath: metadata.annotations['batch.kubernetes.io/job-completion-index']
                  - name: USE_GPUDIRECT
                    value: {gpu_direct_name}
                  - name: GPUS_PER_NODE
                    value: "{chips_per_vm}"
                  - name: COMMAND
                    value: "{args.command}"
                  {custom_envs}"""

  gpu_env_dic = {
      'JAX_COORDINATOR_PORT': '6002',
      'JAX_COORDINATOR_ADDRESS': (
          '$(JOBSET_NAME)-$(REPLICATED_JOB_NAME)-0-0.$(JOBSET_NAME)'
      ),
  }

  args.env = gpu_env_dic | args.env

  return gpu_env_yaml.format(
      args=args,
      chips_per_vm=system.chips_per_vm,
      gpu_direct_name=system.gpu_config.gpu_direct_name,
      custom_envs=format_env_dict(args.env, system),
  )


def get_cpu_env(args, system) -> str:
  """Generate environment variables for CPU nodepools
  Args:
    num_slices: Number of slices to be used in the workload.
    env_vars: Environment variables, processed from user args.
    system: system characteristics

  Returns:
    str: yaml containing env variables
  """
  yaml = """
                - name: REPLICATED_JOB_NAME
                  valueFrom:
                    fieldRef:
                      fieldPath: metadata.annotations['jobset.sigs.k8s.io/replicatedjob-name']
                - name: JOB_INDEX
                  valueFrom:
                    fieldRef:
                      fieldPath: metadata.annotations['jobset.sigs.k8s.io/job-index']
                - name: JOB_COMPLETION_INDEX
                  valueFrom:
                    fieldRef:
                      fieldPath: metadata.annotations['batch.kubernetes.io/job-completion-index']
                {custom_envs}
  """

  cpu_env_dic = {
      'PROCESSES_IN_JOB': str(system.vms_per_slice),
      'JAX_PROCESS_COUNT': str(
          calculate_process_count(args.num_slices, system.vms_per_slice)
      ),
      'JAX_COORDINATOR_ADDRESS': (
          '$(JOBSET_NAME)-$(REPLICATED_JOB_NAME)-0-0.$(JOBSET_NAME)'
      ),
  }

  args.env = cpu_env_dic | args.env

  return yaml.format(custom_envs=format_env_dict(args.env, system))


def format_env_dict(env, system: SystemCharacteristics) -> str:
  if system.accelerator_type == AcceleratorType.GPU:
    # For GPUs, it has two more spaces ahead of name and value respectively
    env_format = '''
                  - name: {key}
                    value: "{value}"'''
  else:
    env_format = '''
                - name: {key}
                  value: "{value}"'''
  return ''.join(env_format.format(key=k, value=v) for k, v in env.items())


def parse_env_config(args, tensorboard_config):
  """Parses the environment configurations to the a dictionary.

  Args:
    args: user provided arguments for running the command.
    tensorboard_config: configuration of Vertex Tensorboard.
    system: system characteristics.
  """
  env = {}

  env_pat = re.compile(r'(^[a-zA-Z_][a-zA-Z0-9_]*?)(?:=(.*))?$', re.M)
  if args.env_file:
    print('Setting container environment from', args.env_file)
    with open(file=args.env_file, mode='r', encoding='utf-8') as f:
      for match in env_pat.finditer(f.read()):
        variable = match.group(1)
        if match.group(2) is not None:
          env[variable] = match.group(2)
        else:
          assert variable in os.environ, (
              f'Variable {variable} is not set in the current '
              'environment, a value must be specified.'
          )
          env[variable] = os.environ[variable]
  if args.env:
    for var in args.env:
      match = env_pat.match(var)
      assert match and match.group(2) is not None, (
          'Invalid environment variable, format must be '
          f'`--env VARIABLE=value`: {var}'
      )
      variable = match.group(1)
      env[variable] = match.group(2)

  if not args.use_pathways:
    if args.debug_dump_gcs:
      if 'XLA_FLAGS' in env:
        raise ValueError(
            'Conflict: XLA_FLAGS defined in both --debug_dump_gcs '
            'and environment file. Please choose one way to define '
            'XLA_FLAGS.'
        )
      env['XLA_FLAGS'] = '--xla_dump_to=/tmp/xla_dump/'

    if tensorboard_config:
      env['UPLOAD_DATA_TO_TENSORBOARD'] = True
      for key, value in tensorboard_config.items():
        env[key.upper()] = value

  args.env = env


def get_volumes(args, system: SystemCharacteristics) -> str:
  """Get volumes accessible to the containers in the pod.
  Args:
    args: user provided args.
    system: system characteristics.

  Returns:
    str:
      YAML for the volumes.
  """
  volumes = """- emptyDir:
                  medium: Memory
                name: dshm-2
              """

  if hasattr(args, 'ramdisk_directory') and args.ramdisk_directory != '':
    driver = 'phase1-checkpoint.csi.storage.gke.io'
    if hasattr(args, 'mtc_enabled') and args.mtc_enabled:
      driver = 'multitier-checkpoint.csi.storage.gke.io'
    volumes += f"""
              - name: cache
                csi:
                  driver: {driver}"""

  if (
      system.accelerator_type == AcceleratorType.TPU
      and args.deploy_stacktrace_sidecar
  ):
    volumes += """
              - name: tpu-stack-trace
              - name: shared-data
              """

  storages: list[Storage] = (
      []
      if is_dry_run()
      else get_storages_to_mount(setup_k8s_env(args), args.storage)
  )
  for storage in storages:
    if storage.type in {
        GCS_FUSE_TYPE,
        GCP_FILESTORE_TYPE,
        PARALLELSTORE_TYPE,
        GCE_PD_TYPE,
        LUSTRE_TYPE,
    }:
      volumes += f"""- name: {storage.pv}
                persistentVolumeClaim:
                  claimName: {storage.pvc}
                  readOnly: {storage.readonly}
              """
  return volumes


def get_volume_mounts(args, system: SystemCharacteristics) -> str:
  """Resources for the main container.
  Args:
    args: user provided args.

  Returns:
    str:
      YAML for the volumes mounted within a Pathways container or GPU container as a YAML string.
  """
  volume_mount_yaml = """- mountPath: /dev/shm
                  name: dshm-2
                """

  if hasattr(args, 'ramdisk_directory') and args.ramdisk_directory != '':
    volume_mount_yaml += f"""
                - mountPath: /{args.ramdisk_directory}
                  name: cache"""

  if args.use_pathways:
    volume_mount_yaml = """- mountPath: /tmp
                  name: shared-tmp
                """
  elif (
      system.accelerator_type == AcceleratorType.TPU
      and args.deploy_stacktrace_sidecar
  ):
    volume_mount_yaml += """- name: tpu-stack-trace
                  mountPath: /tmp/debugging
                - name: shared-data
                  mountPath: /shared-volume
                """
  elif system.accelerator_type == AcceleratorType.GPU:
    volume_mount_yaml = ''

  storages: list[Storage] = (
      []
      if is_dry_run()
      else get_storages_to_mount(setup_k8s_env(args), args.storage)
  )
  for storage in storages:
    if storage.type in {
        GCS_FUSE_TYPE,
        GCP_FILESTORE_TYPE,
        PARALLELSTORE_TYPE,
        GCE_PD_TYPE,
        LUSTRE_TYPE,
    }:
      volume_mount_yaml += f"""- name: {storage.pv}
                  mountPath: {storage.mount_point}
                  readOnly: {storage.readonly}
                """
  return volume_mount_yaml


def calculate_process_count(num_slices, vms_per_slice) -> str:
  """Calculates the total number of processes in the workload.
  Args:
    num_slices: Number of slices to be used in the workload.
    vms_per_slice: number of VMs in each slice.

  Returns:
    str: total number of processes.
  """
  num_processes = int(num_slices) * int(vms_per_slice)

  return f'{num_processes}'


def add_container_ports(args, system: SystemCharacteristics) -> str:
  """Add slice builder and megascale container ports,
  for non-pathways workloads.

  Args:
    args: user provided args.

  Returns:
    str:
      Pathways server port as a YAML string
  """
  port_yaml = """- containerPort: 8471
                - containerPort: 8080"""
  if args.use_pathways:
    return ''

  gpu_port_yaml = """- containerPort: 6002"""
  if system.accelerator_type == AcceleratorType.GPU:
    return gpu_port_yaml
  return port_yaml


def add_jax_coordinator_port(system) -> str:
  """Add jax coordinator port only for CPUs

  Args:
    system: system characteristics.

  Returns:
    str:
      jax coordinator port as a YAML string
  """
  if system.accelerator_type == AcceleratorType.CPU:
    return '- containerPort: 1234'
  return ''


def add_image_pull_policy_for_pw_or_gpu(args, system: SystemCharacteristics):
  """Add image pull policy only for Pathways containers.
  Args:
    args: user provided args.
    system: system characteristics

  Returns:
    str:
      YAML stating that the image will be pulled fro GCR every time.
  """
  yaml = """imagePullPolicy: Always"""

  if args.use_pathways or system.accelerator_type == AcceleratorType.GPU:
    return yaml.format(args=args)
  return ''
