"""
 Copyright 2023 Google LLC

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

r"""Pathways helper functions in XPK.
These functions help support Pathways workloads on XPK.
"""

def add_image_pull_policy_for_pw(args):
  """ Add image pull policy only for Pathways containers.
  Args:
    args: user provided args.

  Returns:
    str:
      YAML stating that the image will be pulled fro GCR every time.
  """
  yaml="""imagePullPolicy: Always"""
  if args.use_pathways:
    return yaml.format(args=args)
  return ""

def get_pw_volume_mounts(args) -> str:
  """ Resources for the main container.
  Args:
    args: user provided args.

  Returns:
    str:
      YAML for the volumes mounted within a Pathways container as a YAML string.
  """
  volume_yaml="""- mountPath: /tmp
                  name: shared-tmp"""
  if args.use_pathways:
    return volume_yaml
  return ""

def get_pathways_rm_args(args) -> str:
  """Arguments for the Pathways resource manager.
  Args:
    args: user provided arguments for running the command.

  Returns:
    str: yaml containing arguments for the Pathways resource manager.
  """
  yaml="""- --alsologtostderr
              - --pathways_server_port=38677
              - --pathways_server_provides_devices=false
              - --pathways_device_type=NONE
              - --pathways_persistent_compilation_cache=false
              - --pathways_compilation_mode=compile_at_worker
              - --pathways_tmp_dir_pattern={args.pathways_gcs_location}
              - --pathways_resource_manager_expected_num_worker_jobs={args.num_slices}"""
  if args.use_pathways:
    return yaml.format(args=args)
  else:
    return ""

def get_pathways_worker_args(args) -> str:
  """Arguments for the Pathways workers.
  Args:
    args: user provided arguments for running the command.

  Returns:
    str: yaml containing arguments for the Pathways workers.
  """
  yaml="""- --alsologtostderr
              - --pathways_server_port=38677
              - --pathways_resource_manager={args.workload}-rm-0-0.{args.workload}:38677
              - --pathways_persistent_compilation_cache=false
              - --pathways_compilation_mode=compile_at_worker
              - --xla_tpu_enable_data_parallel_all_reduce_opt=true
              - --xla_tpu_data_parallel_opt_different_sized_ops=true
              - --xla_tpu_enable_async_collective_fusion=true
              - --xla_tpu_enable_async_collective_fusion_fuse_all_gather=true
              - --xla_tpu_enable_async_collective_fusion_multiple_steps=true
              - --xla_tpu_overlap_compute_collective_tc=true
              - --xla_enable_async_all_gather=true
              - --pathways_tmp_dir_pattern={args.pathways_gcs_location}"""
  if args.use_pathways:
    return yaml.format(args=args)
  else:
    return ""

def get_proxy_args(args) -> str:
  """Arguments for the Pathways proxy.
  Args:
    args: user provided arguments for running the command.

  Returns:
    str: yaml containing arguments for the Pathways proxy.
  """
  yaml="""- --alsologtostderr
              - --v=0
              - --pathways_ifrt_proxy_server_resource_manager={args.workload}-rm-0-0.{args.workload}:38677
              - --pathways_ifrt_proxy_server_port=38676
              - --pathways_tmp_dir_pattern={args.pathways_gcs_location}
              - --pathways_xprof_trace_enable_bulk_upload=true
              - --pathways_plaque_network=gcp"""
  if args.use_pathways:
    return yaml.format(args=args)
  else:
    return ""
