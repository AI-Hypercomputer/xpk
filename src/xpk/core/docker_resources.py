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

from .capacity import H100_DEVICE_TYPE, H100_MEGA_DEVICE_TYPE, H200_DEVICE_TYPE
from .cluster import setup_k8s_env
from .storage import GCS_FUSE_TYPE, GCP_FILESTORE_TYPE, Storage, get_storages_to_mount
from .system_characteristics import AcceleratorType, SystemCharacteristics


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
  if system.accelerator_type == AcceleratorType['GPU']:
    return gpu_resources_yaml.format(system=system)

  if system.accelerator_type == AcceleratorType['CPU']:
    # CPUs don't have chips, but have a subresource called vCPUs.
    # system.chips_per_vm is used as a proxy for vCPUs.
    # Some vCPUs get used in hosting system pods of the workloads,
    # hence an offset of 0.95 is introduced.
    offset_vCPUs = int(system.chips_per_vm) * 0.95
    return f'{resource_type}: {offset_vCPUs}'

  return f'{resource_type}: {system.chips_per_vm}'


def get_env_container(args, system: SystemCharacteristics) -> str:
  """Environment configuration for the main container.
  Args:
    args: user provided args.
    system: system characteristics.

  Returns:
    str:
      YAML with the env config for the main container, as a YAML string.
  """
  pw_env_yaml = """
                - name: XCLOUD_ENVIRONMENT
                  value: GCP
                - name: JAX_PLATFORMS
                  value: proxy
                - name: JAX_BACKEND_TARGET
                  value: {proxy_address}
                - name: JOBSET_NAME
                  valueFrom:
                    fieldRef:
                      fieldPath: metadata.annotations['jobset.sigs.k8s.io/jobset-name']"""
  if args.use_pathways:
    return pw_env_yaml.format(
        args=args, proxy_address=args.pathways_proxy_address
    )

  gpu_env_yaml = """
                  - name: REPLICATED_JOB_NAME
                    valueFrom:
                      fieldRef:
                        fieldPath: metadata.annotations['jobset.sigs.k8s.io/replicatedjob-name']
                  - name: JOBSET_NAME
                    valueFrom:
                      fieldRef:
                        fieldPath: metadata.annotations['jobset.sigs.k8s.io/jobset-name']
                  - name: JAX_COORDINATOR_ADDRESS
                    value: "$(JOBSET_NAME)-$(REPLICATED_JOB_NAME)-0-0.$(JOBSET_NAME)"
                  - name: NNODES
                    value: "{args.num_nodes}"
                  - name: NODE_RANK
                    valueFrom:
                      fieldRef:
                        fieldPath: metadata.annotations['batch.kubernetes.io/job-completion-index']
                  - name: USE_GPUDIRECT
                    value: {gpu_direct_name}
                  - name: GPUS_PER_NODE
                    value: "{system.chips_per_vm}"
                  - name: JAX_COORDINATOR_PORT
                    value: "6002"
                  - name: COMMAND
                    value: "{args.command}"
                  {args.env}"""

  if system.accelerator_type == AcceleratorType['GPU']:
    gpu_direct_name = 'fastrak'
    if args.device_type == H100_DEVICE_TYPE:
      gpu_direct_name = 'tcpx'
      gpu_env_yaml += """
                  - name: LD_LIBRARY_PATH
                    value: /usr/local/nvidia/lib64
"""
    elif args.device_type == H100_MEGA_DEVICE_TYPE:
      gpu_direct_name = 'tcpxo'
    elif args.device_type == H200_DEVICE_TYPE:
      gpu_direct_name = 'rdma'
    return gpu_env_yaml.format(
        args=args, system=system, gpu_direct_name=gpu_direct_name
    )

  if system.accelerator_type == AcceleratorType['CPU']:
    return get_cpu_env(args.num_slices, args.env, system)

  return args.env  # pytype: disable=bad-return-type


def get_cpu_env(num_slices, env_vars, system) -> str:
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
                - name: PROCESSES_IN_JOB
                  value: "{processes_in_job}"
                - name: JAX_PROCESS_COUNT
                  value: "{process_count}"
                {env_vars}
                - name: JAX_COORDINATOR_ADDRESS
                  value: "$(JOBSET_NAME)-$(REPLICATED_JOB_NAME)-0-0.$(JOBSET_NAME)"
  """
  return yaml.format(
      processes_in_job=system.vms_per_slice,
      process_count=calculate_process_count(num_slices, system.vms_per_slice),
      env_vars=env_vars,
  )


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

  if args.ramdisk_directory != '':
    volumes += """
              - name: cache
                csi:
                  driver: phase1-checkpoint.csi.storage.gke.io"""

  if (
      system.accelerator_type == AcceleratorType['TPU']
      and args.deploy_stacktrace_sidecar
  ):
    volumes += """
              - name: tpu-stack-trace
              - name: shared-data
              """

  storages: list[Storage] = get_storages_to_mount(
      setup_k8s_env(args), args.storage
  )
  for storage in storages:
    if storage.type == GCS_FUSE_TYPE:
      volumes += f"""- name: {storage.pv}
                persistentVolumeClaim:
                  claimName: {storage.pvc}
                  readOnly: {storage.readonly}
              """
    if storage.type == GCP_FILESTORE_TYPE:
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

  if args.ramdisk_directory != '':
    volume_mount_yaml += f"""
                - mountPath: /{args.ramdisk_directory}
                  name: cache"""

  if args.use_pathways:
    volume_mount_yaml = """- mountPath: /tmp
                  name: shared-tmp
                """
  elif (
      system.accelerator_type == AcceleratorType['TPU']
      and args.deploy_stacktrace_sidecar
  ):
    volume_mount_yaml += """- name: tpu-stack-trace
                  mountPath: /tmp/debugging
                - name: shared-data
                  mountPath: /shared-volume
                """
  elif system.accelerator_type == AcceleratorType['GPU']:
    if system.device_type == H100_DEVICE_TYPE:
      volume_mount_yaml = """- name: nvidia-install-dir-host
                  mountPath: /usr/local/nvidia/lib64
                - name: tcpx-nccl-plugin-volume
                  mountPath: /usr/local/tcpx
                - name: tcpd-socket
                  mountPath: /tmp
                - name: shared-memory
                  mountPath: /dev/shm
                - name: workload-terminated-volume
                  mountPath: /usr/share/workload"""
    elif (
        system.device_type == H100_MEGA_DEVICE_TYPE
        or system.device_type == H200_DEVICE_TYPE
    ):
      volume_mount_yaml = ''

  storages: list[Storage] = get_storages_to_mount(
      setup_k8s_env(args), args.storage
  )
  for storage in storages:
    if storage.type == GCS_FUSE_TYPE:
      volume_mount_yaml += f"""- name: {storage.pv}
                  mountPath: {storage.mount_point}
                  readOnly: {storage.readonly}
                """
    if storage.type == GCP_FILESTORE_TYPE:
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
  if system.accelerator_type == AcceleratorType['GPU']:
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
  if system.accelerator_type == AcceleratorType['CPU']:
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

  if args.use_pathways or system.accelerator_type == AcceleratorType['GPU']:
    return yaml.format(args=args)
  return ''
