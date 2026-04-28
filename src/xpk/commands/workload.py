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

import urllib
import argparse
from ..core.system_characteristics import SystemCharacteristics
from ..core.blueprint.blueprint_generator import (
    a3high_device_type,
    a4x_device_types,
)
from ..core.cluster import (
    XPK_SA,
    setup_k8s_service_accounts,
    get_cluster_credentials,
    setup_k8s_env,
)
from ..core.commands import run_command_with_updates, run_commands, run_command_for_value
from ..core.config import (VERTEX_TENSORBOARD_FEATURE_FLAG, XPK_CURRENT_VERSION)
from ..core.docker_container import (
    get_main_container_docker_image,
    get_user_workload_container,
)
from ..core.kueue_manager import LOCAL_QUEUE_NAME, derive_k8s_workload_name
from ..core.poc_discovery import (
    CONFIG_CM_NAME,
    CONFIG_CM_NAMESPACE,
    available_teams,
    available_value_classes,
    fetch_poc_config,
    max_k8s_workload_name_len,
    resolve_team,
    suggest,
)
from ..core.docker_resources import get_volumes, parse_env_config
from ..core.gcloud_context import add_zone_and_project
from ..core.monitoring import get_gke_outlier_dashboard
from ..core.nap import (
    get_autoprovisioning_node_selector_args,
    is_autoprovisioning_enabled,
)
from ..core.network import get_cluster_subnetworks
from ..core.pathways import (
    check_if_pathways_job_is_installed,
    ensure_pathways_workload_prerequisites,
    get_pathways_unified_query_link,
    try_to_delete_pathwaysjob_first,
)
from ..core.resources import get_cluster_capacity_type, get_cluster_system_characteristics_from_config_map
from ..core.resources import ConfigMapType, get_cluster_configmap
from ..core.nodepool import ensure_resource_policy_exists
from ..core.scheduling import (
    ONE_TO_ONE_REPLICA_NODE_POOL_ASSIGNMENT_ANNOTATION,
    WorkloadScheduling,
    check_if_workload_can_schedule,
    create_tpu_slice_topology_annotation,
    get_cpu_affinity,
    get_gpu_scheduler,
    create_sub_slicing_annotations,
    create_placement_policy_label,
    get_placement_policy_name,
    is_placement_policy_supported,
)
from ..core.storage import (
    GCE_PD_TYPE,
    GCP_FILESTORE_TYPE,
    GCS_FUSE_TYPE,
    PARALLELSTORE_TYPE,
    LUSTRE_TYPE,
    Storage,
    add_bucket_iam_members,
    get_storage_annotations,
    get_storages_to_mount,
)
from ..core.system_characteristics import (
    AcceleratorType,
    create_accelerator_label,
    create_machine_label,
    get_system_characteristics,
)
from ..core.vertex import create_vertex_experiment
from ..core.workload import (
    check_if_workload_exists,
    get_jobsets_list_gcp_link,
    get_workload_list,
    wait_for_job_completion,
    get_cluster_location,
)
from ..core.workload_decorators import (
    storage_decorator,
)
from ..utils.console import ask_for_user_consent, xpk_exit, xpk_print
from ..utils.file import write_tmp_file
from ..utils.execution_context import is_dry_run
from ..utils.feature_flags import FeatureFlags
from ..utils.validation import validate_dependencies_list, SystemDependency, should_validate_dependencies
from . import cluster_gcluster
from .common import is_GPU_TAS_possible
from jinja2 import Environment, FileSystemLoader
from ..utils.templates import get_templates_absolute_path

_PATHWAYS_WORKLOAD_TEMPLATE = 'pathways_workload_create.yaml.j2'

_SUPER_SLICING_WORKLOAD_NAME_LIMIT = 28


def _load_poc_cfg(args) -> dict | None:
  """Fetch the PoC ConfigMap once per invocation and cache on args. Returns
  None if --team is unset (so upstream, non-PoC behavior is preserved)."""
  if not getattr(args, 'team', None):
    return None
  cached = getattr(args, '_poc_cfg', None)
  if cached is not None:
    return cached
  cfg = fetch_poc_config()
  if cfg is None:
    xpk_print(
        f'ERROR: --team={args.team!r} requires the PoC ConfigMap'
        f' "{CONFIG_CM_NAMESPACE}/{CONFIG_CM_NAME}" on the target cluster.'
        ' Deploy cluster-management/poc/chart first, or drop --team to bypass'
        ' PoC routing.'
    )
    xpk_exit(1)
  if args.team not in (cfg.get('teams') or {}):
    teams = available_teams(cfg)
    hints = suggest(args.team, teams)
    hint_line = f' Did you mean: {", ".join(hints)}?' if hints else ''
    xpk_print(
        f'ERROR: --team={args.team!r} not found on this cluster.{hint_line}'
        f' Available teams: {", ".join(teams) or "<none>"}'
    )
    xpk_exit(1)
  if getattr(args, 'value_class', None):
    vcs = available_value_classes(cfg)
    if vcs and args.value_class not in vcs:
      hints = suggest(args.value_class, vcs)
      hint_line = f' Did you mean: {", ".join(hints)}?' if hints else ''
      xpk_print(
          f'ERROR: --value-class={args.value_class!r} not valid on this cluster.'
          f'{hint_line} Available: {", ".join(vcs)}'
      )
      xpk_exit(1)
  args._poc_cfg = cfg
  return cfg


def _resolve_poc_team(args) -> tuple[str, str, str]:
  """Return (namespace, local_queue_name, priority_class) for --team, or defaults."""
  cfg = _load_poc_cfg(args)
  if cfg is None:
    return ('', LOCAL_QUEUE_NAME, args.priority)
  return resolve_team(cfg, args.team)


def _build_poc_labels(args) -> str:
  """Return YAML label lines for PoC quota labels, or empty string."""
  if not getattr(args, 'team', None):
    return ''
  lines = [f'team: {args.team}']
  if getattr(args, 'value_class', None):
    lines.append(f'value-class: {args.value_class}')
  if getattr(args, 'declared_duration_minutes', None) is not None:
    lines.append(f'declared-duration-minutes: "{args.declared_duration_minutes}"')
  # indent to match template (4 spaces)
  return ('\n    ').join(lines)


def _build_poc_pod_template_labels(args) -> str:
  """Return YAML label lines for PoC labels that must appear in pod template.

  Kueue does NOT propagate arbitrary JobSet metadata labels to the Workload
  object, so the time-limit controller reads declared-duration-minutes from
  spec.podSets[*].template.metadata.labels instead.
  """
  if not getattr(args, 'team', None):
    return ''
  if getattr(args, 'declared_duration_minutes', None) is None:
    return ''
  # indent to match pod template labels (16 spaces)
  return f'declared-duration-minutes: "{args.declared_duration_minutes}"'


"""Maximum safe workload name length to avoid exceeding GCE's 63-character limit.

Kueue/Jobset prefixes and suffixes consume characters: 8 (`default-`), 7 (`jobset-`),
11 (Kueue hash), and 9 (NAP/GKE hash). Maximum safe length is 63 - 8 - 7 - 11 - 9 = 28.
"""

WORKLOAD_CREATE_YAML = """apiVersion: jobset.x-k8s.io/v1alpha2
kind: JobSet
metadata:
  name: {k8s_name}
  {namespace_field}
  labels:
    kueue.x-k8s.io/queue-name: {local_queue_name}  # Name of the LocalQueue
    xpk.google.com/workload: {args.workload}
    {poc_labels}
  annotations:
    {jobset_annotations}
spec:
  ttlSecondsAfterFinished: {args.ttl_seconds_after_finished}
  failurePolicy:
    {failure_policy_rules}
    maxRestarts: {args.max_restarts}
  replicatedJobs:
    - name: slice-job
      replicas: {args.num_slices}
      template:
        spec:
          parallelism: {vms_per_slice}    # Equal to the number of VMs per slice (or sub-slice).
          completions: {vms_per_slice}    # Same as the above.
          backoffLimit: 0   # When any pod fails, the job is failed
          {pod_failure_policy}
          template:
            metadata:
              labels:
                xpk.google.com/workload: {args.workload}
                {poc_pod_template_labels}
              annotations:
                {storage_annotations}
                {sub_slicing_annotations}
                {tpu_slice_topology_annotation}
            spec:
              schedulerName: {args.scheduler}
              imagePullSecrets:
              - name: {args.docker_image_pull_secret}
              restartPolicy: Never
              {affinity}
              nodeSelector:
                {accelerator_label}
                {node_selector_machine_label}
                {placement_policy_label}
                {autoprovisioning_args}
              priorityClassName: {args.priority}
              hostNetwork: true
              dnsPolicy: ClusterFirstWithHostNet
              terminationGracePeriodSeconds: {args.termination_grace_period_seconds}
              containers:
              {container}
              serviceAccountName: {service_account}
              tolerations:
              {tpu_toleration}
              volumes:
              {volumes}
"""


GPU_WORKLOAD_CREATE_YAML = """apiVersion: jobset.x-k8s.io/v1alpha2
kind: JobSet
metadata:
  name: {args.workload}
  annotations:
    {storage_annotations}
  labels:
    kueue.x-k8s.io/queue-name: multislice-queue  # Name of the LocalQueue
    xpk.google.com/workload: {args.workload}
spec:
  ttlSecondsAfterFinished: {args.ttl_seconds_after_finished}
  failurePolicy:
    {failure_policy_rules}
    maxRestarts: {args.max_restarts}
  replicatedJobs:
    - name: slice-job
      replicas: 1
      template:
        metadata:
          annotations:
            {storage_annotations}
        spec:
          parallelism: {args.num_nodes}
          completions: {args.num_nodes}
          backoffLimit: 0   # When any pod fails, the job is failed
          {pod_failure_policy}
          template:
            metadata:
              labels:
                xpk.google.com/workload: {args.workload}
            spec:
              {gpu_scheduler}
              priorityClassName: {args.priority}
              restartPolicy: Never
              nodeSelector:
                {placement_policy_label}
              imagePullSecrets:
              - name: {args.docker_image_pull_secret}
              hostNetwork: true
              dnsPolicy: ClusterFirstWithHostNet
              terminationGracePeriodSeconds: {args.termination_grace_period_seconds}
              serviceAccountName: {service_account}
              tolerations:
              - operator: "Exists"
                key: nvidia.com/gpu
              volumes:
              {volumes}
              containers:
              {container}
"""

A3_GPU_WORKLOAD_CREATE_YAML = """apiVersion: jobset.x-k8s.io/v1alpha2
kind: JobSet
metadata:
  name: {args.workload}
  labels:
    kueue.x-k8s.io/queue-name: multislice-queue  # Name of the LocalQueue
    xpk.google.com/workload: {args.workload}
spec:
  ttlSecondsAfterFinished: {args.ttl_seconds_after_finished}
  failurePolicy:
    {failure_policy_rules}
    maxRestarts: {args.max_restarts}
  replicatedJobs:
    - name: slice-job
      replicas: 1
      template:
        spec:
          parallelism: {args.num_nodes}
          completions: {args.num_nodes}
          backoffLimit: 0   # When any pod fails, the job is failed
          {pod_failure_policy}
          template:
            metadata:
              labels:
                xpk.google.com/workload: {args.workload}
              annotations:
                {annotations}
            spec:
              priorityClassName: {args.priority}
              restartPolicy: Never
              nodeSelector:
                {placement_policy_label}
              imagePullSecrets:
              - name: {args.docker_image_pull_secret}
              dnsPolicy: ClusterFirstWithHostNet
              terminationGracePeriodSeconds: {args.termination_grace_period_seconds}
              serviceAccountName: {service_account}
              tolerations:
              - operator: "Exists"
                key: nvidia.com/gpu
              containers:
              {container}
"""

ARM_GPU_WORKLOAD_CREATE_JINJA_FILE = 'arm_gpu_workload_crate.yaml.j2'


def _generate_pathways_workload_yaml(
    args: argparse.Namespace,
    workload_system: SystemCharacteristics,
    parallel_containers: int,
    placement_policy_label: str,
    autoprovisioning_args: str | None,
    node_selector_machine_label: str,
    tpu_slice_topology_annotation: str,
    jobset_annotations: str,
) -> str:
  worker_backoff_limit = (
      (args.max_slice_restarts * workload_system.vms_per_slice)
      if getattr(args, 'elastic_slices', 0) > 0
      else (workload_system.vms_per_slice * 4)
  )

  proxy_server_image = (
      getattr(args, 'proxy_server_image', None)
      or 'us-docker.pkg.dev/cloud-tpu-v2-images/pathways/proxy_server:latest'
  )
  server_image = (
      getattr(args, 'server_image', None)
      or 'us-docker.pkg.dev/cloud-tpu-v2-images/pathways/server:latest'
  )
  worker_image = getattr(args, 'worker_image', None) or server_image
  instance_type = (
      f'{workload_system.pathways_tpu_version}:{workload_system.topology}'
      if workload_system.pathways_tpu_version
      else workload_system.gce_machine_type
  )
  if args.headless:
    user_workload_container = ''
    user_workload_env_vars = []
  else:
    user_workload_container, _ = get_user_workload_container(
        args, workload_system, parallel_containers
    )

    user_workload_env_vars = [
        {
            'name': 'PATHWAYS_HEAD',
            'valueFrom': "metadata.labels['jobset.sigs.k8s.io/coordinator']",
        },
        {
            'name': 'JAX_PLATFORMS',
            'value': 'proxy',
        },
        {
            'name': 'XCLOUD_ENVIRONMENT',
            'value': 'GCP',
        },
        {
            'name': 'JAX_BACKEND_TARGET',
            'value': 'grpc://$(PATHWAYS_HEAD):29000',
        },
    ]

  template_env = Environment(
      loader=FileSystemLoader(searchpath=get_templates_absolute_path()),
      trim_blocks=True,
      lstrip_blocks=True,
      keep_trailing_newline=True,
  )
  workload_create_yaml = template_env.get_template(_PATHWAYS_WORKLOAD_TEMPLATE)
  return workload_create_yaml.render(
      args=args,
      local_queue_name=LOCAL_QUEUE_NAME,
      proxy_server_image=proxy_server_image,
      server_image=server_image,
      instance_type=instance_type,
      user_workload_container=user_workload_container,
      user_workload_env_vars=user_workload_env_vars,
      worker_backoff_limit=worker_backoff_limit,
      vms_per_slice=workload_system.vms_per_slice,
      workload_system=workload_system,
      accelerator_label=create_accelerator_label(workload_system),
      node_selector_machine_label=node_selector_machine_label,
      tpu_slice_topology_annotation=tpu_slice_topology_annotation,
      jobset_annotations=jobset_annotations,
      placement_policy_label=placement_policy_label,
      autoprovisioning_args=autoprovisioning_args,
      worker_image=worker_image,
      is_tpu=workload_system.accelerator_type == AcceleratorType.TPU,
  )


def workload_create_pathways(args) -> None:
  """Run jobset apply command for a file, specifically for Pathways.

  Args:
    args: user provided arguments for running the command.

  Returns:
    0 if successful and 1 otherwise.
  """
  args.use_pathways = True
  if args.headless:
    xpk_print(
        'Please use kubectl port forwarding to connect to the Pathways proxy.'
        ' kubectl get pods kubectl port-forward <proxy-pod-name> 29000:29000'
        ' JAX_PLATFORMS=proxy JAX_BACKEND_TARGET=grpc://127.0.0.1:29000 python'
        " -c 'import pathwaysutils; import jax; print(jax.devices())'"
    )
  workload_create(args)


def workload_create(args) -> None:
  """Run jobset apply command for a file.

  Args:
    args: user provided arguments for running the command.

  Returns:
    0 if successful and 1 otherwise.
  """
  if should_validate_dependencies(args):
    validate_dependencies_list(
        args,
        [
            SystemDependency.KUBECTL,
            SystemDependency.GCLOUD,
            SystemDependency.DOCKER
            if not FeatureFlags.CRANE_WORKLOADS_ENABLED
            else SystemDependency.CRANE,
        ],
    )
  k8s_api_client = None
  if not is_dry_run():
    k8s_api_client = setup_k8s_env(args)
    setup_k8s_service_accounts()

  workload_exists = check_if_workload_exists(args)

  if workload_exists:
    will_delete = ask_for_user_consent(
        f'{args.workload} already exists, do you want to overwrite it?'
    )
    if will_delete:
      xpk_print(f'Deleting {args.workload} to overwrite it...')
      return_code = delete_workloads(args, [args.workload])
      if return_code != 0:
        xpk_print(f'Delete Workload request returned ERROR {return_code}')
        xpk_exit(return_code)
    else:
      xpk_print(
          f'{args.workload} already exists, XPK will not create this workload.'
          ' Please pick a new workload name'
      )
      xpk_exit(1)

  workload_system, return_code = get_system_characteristics(args)
  if return_code > 0 or workload_system is None:
    xpk_print('Fetching system characteristics failed!')
    xpk_exit(return_code)

  resources_config_map = get_cluster_configmap(
      args.cluster, ConfigMapType.RESOURCES
  )
  cluster_system = get_cluster_system_characteristics_from_config_map(
      resources_config_map
  )
  workload_scheduling = check_if_workload_can_schedule(
      args=args,
      workload_system=workload_system,
      cluster_system=cluster_system,
      resources_config_map=resources_config_map,
  )
  if workload_scheduling == WorkloadScheduling.UNAVAILABLE:
    xpk_exit(1)

  xpk_print('Starting workload create', flush=True)

  cluster_config_map = get_cluster_configmap(
      args.cluster, ConfigMapType.METADATA
  )
  cluster_xpk_version = None
  if cluster_config_map is None:
    xpk_print(
        'Warning: Unable to find ConfigMap for the'
        ' cluster. We recommend to upgrade your cluster by running `xpk'
        ' cluster create`.'
    )
  else:
    cluster_xpk_version = cluster_config_map.get('xpk_version')
  if (
      cluster_xpk_version is not None
      and cluster_xpk_version != XPK_CURRENT_VERSION
  ):
    xpk_print(
        'Warning: Cluster has been created using XPK version:'
        f' {cluster_xpk_version} but the XPK version you are'
        f' using to schedule workload is: {XPK_CURRENT_VERSION}. Some features'
        ' might not be available for this cluster. We recommend to'
        ' upgrade/downgrade your XPK version or cluster by running `xpk'
        ' cluster create`.'
    )

  debugging_dashboard_id = None

  tensorboard_config: dict | None = {}
  if VERTEX_TENSORBOARD_FEATURE_FLAG and args.use_vertex_tensorboard:
    tensorboard_config = create_vertex_experiment(args)
    # exit if failed to create Experiment in Vertex AI
    if not tensorboard_config:
      xpk_exit(1)

  parse_env_config(args, tensorboard_config)

  # For PoC teams, inject the user's full display name as XPK_WORKLOAD_NAME so
  # training scripts can reference it for GCS artifact paths regardless of the
  # short K8s name xpk derives for the JobSet.
  if getattr(args, 'team', None):
    args.env.setdefault('XPK_WORKLOAD_NAME', args.workload)

  autoprovisioning_args = ''
  autoprovisioning_enabled, return_code = is_autoprovisioning_enabled(
      args, workload_system
  )
  if return_code != 0:
    xpk_exit(return_code)
  if autoprovisioning_enabled:
    # Determine NAP capacity type
    autoprovisioning_args, return_code = (
        get_autoprovisioning_node_selector_args(args)
    )
    if return_code != 0:
      xpk_exit(return_code)

  service_account = ''
  all_storages = []
  # Currently storage customization is not supported for Pathways workloads. b/408468941
  if not args.use_pathways:
    storages: list[Storage] = (
        []
        if k8s_api_client is None
        else get_storages_to_mount(k8s_api_client, args.storage)
    )
    gcs_fuse_storages = list(
        filter(lambda storage: storage.type == GCS_FUSE_TYPE, storages)
    )
    gcpfilestore_storages: list[Storage] = list(
        filter(lambda storage: storage.type == GCP_FILESTORE_TYPE, storages)
    )
    parallelstore_storages: list[Storage] = list(
        filter(lambda storage: storage.type == PARALLELSTORE_TYPE, storages)
    )
    pd_storages: list[Storage] = list(
        filter(lambda storage: storage.type == GCE_PD_TYPE, storages)
    )
    lustre_storages: list[Storage] = list(
        filter(lambda storage: storage.type == LUSTRE_TYPE, storages)
    )
    if len(gcs_fuse_storages) > 0:
      service_account = XPK_SA
      xpk_print(f'Detected gcsfuse Storages to add: {gcs_fuse_storages}')
    else:
      xpk_print('No gcsfuse Storages to add detected')

    if len(gcpfilestore_storages) > 0:
      service_account = XPK_SA
      xpk_print(
          f'Detected gcp filestores instances to add: {gcpfilestore_storages}'
      )
    else:
      xpk_print('No gcp filestore instances to add detected.')

    if len(parallelstore_storages) > 0:
      service_account = XPK_SA
      xpk_print(
          'Detected gcp parallelstore instances to add:'
          f' {parallelstore_storages}'
      )
    else:
      xpk_print('No gcp parallelstore instances to add detected.')

    if len(pd_storages) > 0:
      service_account = XPK_SA
      xpk_print(f'Detected gce persistent disk instances to add: {pd_storages}')
    else:
      xpk_print('No gce persistent disk instances to add detected.')

    if len(lustre_storages) > 0:
      service_account = XPK_SA
      xpk_print(f'Detected managed lustre instances to add: {lustre_storages}')
    else:
      xpk_print('No managed lustre instances to add detected.')

    all_storages = (
        gcs_fuse_storages
        + gcpfilestore_storages
        + parallelstore_storages
        + pd_storages
        + lustre_storages
    )

  use_sub_slicing = (
      workload_scheduling == WorkloadScheduling.SUB_SLICING_AVAILABLE
  )
  use_super_slicing = (
      workload_scheduling == WorkloadScheduling.SUPER_SLICING_AVAILABLE
  )

  if (
      use_super_slicing
      and not getattr(args, 'team', None)
      and len(args.workload) > _SUPER_SLICING_WORKLOAD_NAME_LIMIT
  ):
    xpk_print(
        'Error: For super-slicing workloads, the workload name cannot exceed'
        f' {_SUPER_SLICING_WORKLOAD_NAME_LIMIT} characters due to'
        ' Kubernetes/GCE resource name limits. The provided name'
        f' `{args.workload}` is {len(args.workload)} characters.'
    )
    xpk_exit(1)

  parallel_containers = workload_system.parallel_containers
  if not args.use_parallel_containers or args.use_pathways:
    parallel_containers = 1

  # Currently failure policy rules are supported for Pathways workloads. b/408465881
  failure_policy_rules = ''
  pod_failure_policy = ''
  if not args.use_pathways:
    failure_policy_rules = """rules:
      - action: FailJobSet
        onJobFailureReasons:
        - PodFailurePolicy"""
    restart_on_exit_codes_list = get_restart_exit_codes(args)
    restart_on_exit_codes = ','.join(map(str, restart_on_exit_codes_list))

    pod_failure_policy = """
          podFailurePolicy:
            rules:
          """
    docker_image = get_main_container_docker_image(args, workload_system)
    for i in range(parallel_containers):
      docker_image_sufix = f'-{i + 1}' if parallel_containers > 1 else ''
      pod_failure_policy += f"""
            - action: FailJob
              onPodConditions: []
              onExitCodes:
                containerName: {docker_image}{docker_image_sufix}
                operator: NotIn
                values: [{restart_on_exit_codes}]"""

  placement_policy_label = ''
  if (
      # Don't bother with placement for sub/super-slicing workloads:
      workload_scheduling == WorkloadScheduling.AVAILABLE
      and is_placement_policy_supported(workload_system)
  ):
    ensure_resource_policy_exists(
        resource_policy_name=get_placement_policy_name(
            workload_system, super_slicing=False
        ),
        project=args.project,
        zone=args.zone,
        topology=workload_system.topology,
        super_slicing=False,
    )
    placement_policy_label = create_placement_policy_label(
        workload_system, super_slicing=False
    )

  # TODO(b/466943057): Add ANP label for NAP (if not possible, use CCC)

  if use_sub_slicing:
    xpk_print('Workload will be scheduled using the Sub-slicing feature.')
  if use_super_slicing:
    xpk_print('Workload will be scheduled using the Super-slicing feature.')

  machine_label = (
      create_machine_label(cluster_system)
      if use_sub_slicing and cluster_system
      else create_machine_label(workload_system)
  )
  node_selector_machine_label = machine_label if not use_super_slicing else ''
  tpu_slice_topology_annotation = (
      create_tpu_slice_topology_annotation(workload_system.topology)
      if use_super_slicing
      else ''
  )
  jobset_annotations = (
      ''
      if use_super_slicing or use_sub_slicing
      else ONE_TO_ONE_REPLICA_NODE_POOL_ASSIGNMENT_ANNOTATION
  )

  # Create the workload file based on accelerator type or workload type.
  if workload_system.accelerator_type == AcceleratorType.GPU:
    container, debugging_dashboard_id = get_user_workload_container(
        args, workload_system, parallel_containers=parallel_containers
    )
    gpu_scheduler, return_code = get_gpu_scheduler(
        args, workload_system, autoprovisioning_args
    )
    if return_code != 0:
      xpk_exit(return_code)
    capacity_type = get_cluster_capacity_type(args)

    annotations = (
        'kueue.x-k8s.io/podset-preferred-topology: "kubernetes.io/hostname"'
        if is_GPU_TAS_possible(
            cluster_system, capacity_type, args.cluster, args.zone, args.project
        )
        else ''
    )

    if (
        workload_system.device_type in cluster_gcluster.supported_device_types
        or workload_system.device_type == a3high_device_type
        or workload_system.device_type in a4x_device_types
    ):
      if workload_system.device_type in a4x_device_types:
        template_env = Environment(
            loader=FileSystemLoader(searchpath=get_templates_absolute_path())
        )
        workload_create_yaml = template_env.get_template(
            ARM_GPU_WORKLOAD_CREATE_JINJA_FILE
        )
        yml_string = workload_create_yaml.render(
            workload=args.workload,
            num_nodes=args.num_nodes,
            ttl_seconds_after_finished=args.ttl_seconds_after_finished,
            max_restarts=args.max_restarts,
            priority=args.priority,
            termination_grace_period_seconds=args.termination_grace_period_seconds,
            docker_image_pull_secret=args.docker_image_pull_secret,
            container=container,
            service_account=XPK_SA,
            failure_policy_rules=failure_policy_rules,
            pod_failure_policy=pod_failure_policy,
            annotations=annotations,
            placement_policy_label=placement_policy_label,
        )
      else:
        yml_string = A3_GPU_WORKLOAD_CREATE_YAML.format(
            args=args,
            container=container,
            service_account=XPK_SA,
            failure_policy_rules=failure_policy_rules,
            pod_failure_policy=pod_failure_policy,
            annotations=annotations,
            placement_policy_label=placement_policy_label,
        )

      sub_networks = get_cluster_subnetworks()

      if workload_system.gpu_config and callable(
          workload_system.gpu_config.jobset_decorator_fn
      ):
        decorator_fn = workload_system.gpu_config.jobset_decorator_fn
        yml_string = decorator_fn(yml_string, sub_networks)

      if all_storages:
        yml_string = storage_decorator.decorate_jobset(yml_string, all_storages)
    else:
      yml_string = GPU_WORKLOAD_CREATE_YAML.format(
          args=args,
          container=container,
          gpu_scheduler=gpu_scheduler,
          volumes=get_volumes(args, workload_system),
          storage_annotations=('\n' + (' ' * 12)).join(
              get_storage_annotations(all_storages)
          ),
          service_account=service_account,
          failure_policy_rules=failure_policy_rules,
          pod_failure_policy=pod_failure_policy,
          placement_policy_label=placement_policy_label,
      )

  elif args.use_pathways and ensure_pathways_workload_prerequisites(
      args, workload_system
  ):
    yml_string = _generate_pathways_workload_yaml(
        args=args,
        workload_system=workload_system,
        parallel_containers=parallel_containers,
        placement_policy_label=placement_policy_label,
        autoprovisioning_args=autoprovisioning_args,
        node_selector_machine_label=node_selector_machine_label,
        tpu_slice_topology_annotation=tpu_slice_topology_annotation,
        jobset_annotations=jobset_annotations,
    )
  else:
    container, debugging_dashboard_id = get_user_workload_container(
        args, workload_system, parallel_containers
    )

    poc_namespace, poc_local_queue, poc_priority = _resolve_poc_team(args)
    # Derive a short K8s-safe JobSet name for PoC teams; use display name as-is otherwise.
    if poc_namespace:
      max_len = max_k8s_workload_name_len(args._poc_cfg, poc_namespace)
      k8s_name = derive_k8s_workload_name(args.workload, max_len)
      args.priority = poc_priority
      xpk_print(
          f'PoC workload "{args.workload}" → K8s JobSet name: "{k8s_name}"'
          f' (use $XPK_WORKLOAD_NAME in your command for GCS artifact paths)'
      )
    else:
      k8s_name = args.workload
    yml_string = WORKLOAD_CREATE_YAML.format(
        args=args,
        k8s_name=k8s_name,
        jobset_annotations=jobset_annotations,
        container=container,
        vms_per_slice=workload_system.vms_per_slice,
        affinity=get_cpu_affinity(workload_system.accelerator_type),
        accelerator_label=create_accelerator_label(workload_system),
        sub_slicing_annotations=(
            ('\n' + (' ' * 16)).join(
                create_sub_slicing_annotations(workload_system.topology)
            )
            if use_sub_slicing
            else ''
        ),
        placement_policy_label=placement_policy_label,
        node_selector_machine_label=node_selector_machine_label,
        tpu_slice_topology_annotation=tpu_slice_topology_annotation,
        local_queue_name=poc_local_queue,
        namespace_field=f'namespace: {poc_namespace}' if poc_namespace else '',
        poc_labels=_build_poc_labels(args),
        poc_pod_template_labels=_build_poc_pod_template_labels(args),
        autoprovisioning_args=autoprovisioning_args,
        volumes=get_volumes(args, workload_system),
        storage_annotations=('\n' + (' ' * 16)).join(
            get_storage_annotations(all_storages)
        ),
        service_account=service_account,
        tpu_toleration="""
              - operator: "Exists"
                key: google.com/tpu
        """ if workload_system.accelerator_type == AcceleratorType.TPU else '',
        failure_policy_rules=failure_policy_rules,
        pod_failure_policy=pod_failure_policy,
    )
  if args.output_manifest_file:
    with open(args.output_manifest_file, 'w', encoding='utf-8') as f:
      f.write(yml_string)
    xpk_print(
        f'Workload {args.workload} manifest written to'
        f' {args.output_manifest_file}'
    )

  tmp = write_tmp_file(yml_string)
  command = f'kubectl apply -f {str(tmp)}'
  return_code = run_command_with_updates(command, 'Creating Workload')

  if return_code != 0:
    xpk_print(f'Create Workload request returned ERROR {return_code}')
    xpk_exit(return_code)

  if not args.use_pathways and not is_dry_run():
    add_bucket_iam_members(args, storages)

  # Get GKE outlier dashboard for TPU
  outlier_dashboard_id = None
  if workload_system.accelerator_type == AcceleratorType.TPU:
    outlier_dashboard_id = get_gke_outlier_dashboard(args)

  # Outlier and debugging dashboards
  if outlier_dashboard_id is not None:
    xpk_print(
        'Check statistics and outlier mode of GKE metrics here:'
        # pylint: disable=line-too-long
        f' https://console.cloud.google.com/monitoring/dashboards/builder/{outlier_dashboard_id}?project={args.project}&f.rlabel.cluster_name.ClusterName={args.cluster}.'
        ' To view the metric data for your workload, select'
        f' {args.workload} from the JobName filter on the dashboard.'
    )

  if debugging_dashboard_id is not None:
    xpk_print(
        'Check stack traces collected in Cloud Logging here:'
        # pylint: disable=line-too-long
        f' https://console.cloud.google.com/monitoring/dashboards/builder/{debugging_dashboard_id}?project={args.project}&f.rlabel.cluster_name.ClusterName={args.cluster}.'
        ' To view the stack traces for your workload, select'
        f' {args.workload} from the JobName filter on the dashboard.'
    )

  if args.use_pathways:
    if args.headless:
      xpk_print(
          '******* Please use kubectl port forwarding to connect to the'
          ' Pathways proxy, once you see "IFRT proxy server started with status'
          ' OK" on the proxy link below. Remember to delete the workload once'
          ' done! ******* '
      )
      xpk_print(
          'Steps to connect to the proxy: kubectl get pods | grep proxy ;'
          ' kubectl port-forward <proxy-pod-name> 29000:29000; '
          ' JAX_PLATFORMS=proxy; JAX_BACKEND_TARGET=grpc://127.0.0.1:29000;'
          " python -c 'import pathwaysutils; import jax; print(jax.devices())'"
      )
      pathways_proxy_link = (
          f'https://console.cloud.google.com/kubernetes/job/{get_cluster_location(args.project, args.cluster, args.zone)}/{args.cluster}/default/{args.workload}-proxy-0/details?project={args.project}'
      )
      xpk_print(
          'Follow the proxy here:'
          # pylint: disable=line-too-long)
          f' {pathways_proxy_link} '
      )
    xpk_print(
        'Follow your Pathways workload and other resources here: '
        f'{get_pathways_unified_query_link(args)}'
    )
  else:
    xpk_print(
        'Follow your workload here:'
        # pylint: disable=line-too-long
        f' https://console.cloud.google.com/kubernetes/service/{get_cluster_location(args.project, args.cluster, args.zone)}/{args.cluster}/default/{args.workload}/details?project={args.project}'
    )
    duration_of_logs = 'P1D'  # Past 1 Day
    log_filter = (
        'resource.type="k8s_container"\n'
        f'resource.labels.project_id="{args.project}"\n'
        f'resource.labels.location="{get_cluster_location(args.project, args.cluster, args.zone)}"\n'
        f'resource.labels.cluster_name="{args.cluster}"\n'
        'resource.labels.namespace_name="default"\n'
        f'resource.labels.pod_name:"{args.workload}-slice-job-0-0-"\n'
        'severity>=DEFAULT'
    )
    encoded_filter = urllib.parse.quote(log_filter, safe='')
    xpk_print(
        'Follow your worker 0, slice 0 logs here:'
        ' Adjust the pod name'
        ' ([prefix]-slice-job-[slice_number]-[worker_number])'
        ' after clicking the url if you want other worker logs.'
        ' https://console.cloud.google.com/logs/query;'
        f'query={encoded_filter};'
        'storageScope=project;'
        f'duration={duration_of_logs}?'
        f'project={args.project}'
    )

  xpk_exit(0)


def get_restart_exit_codes(args) -> list:
  exit_codes = [42]
  exit_codes.extend(range(127, 256, 1))

  if args.restart_on_exit_codes is not None:
    items = args.restart_on_exit_codes.split(',')
    for item in items:
      item = item.strip()
      if '-' in item:
        start, end = map(int, item.split('-'))
        exit_codes.extend(range(start, end + 1))
      else:
        exit_codes.append(int(item))

  # Remove duplicates that the user may have added.
  return list(set(exit_codes))


def delete_workloads(args, workloads: list[str]) -> int:
  """Helper function to delete workloads.

  Args:
    args: user provided arguments for running the command.
    workloads: list of workloads to delete.

  Returns:
    0 if successful and non-zero otherwise.
  """
  # If PathwaysJob exists, delete it.
  if check_if_pathways_job_is_installed(
      args
  ) and try_to_delete_pathwaysjob_first(args, workloads):
    return 0
  # PathwaysJob workload does not exist, delete JobSet
  commands = []
  task_names = []
  for workload in workloads:
    args.workload = workload
    command = f'kubectl delete jobset {workload} -n default'
    task_name = f'WorkloadDelete-{workload}'
    commands.append(command)
    task_names.append(task_name)

  # Not batching deletion for single workload
  if len(workloads) == 1:
    return_code = run_command_with_updates(commands[0], 'Delete Workload')
  else:
    maybe_failure = run_commands(
        commands,
        'Delete Workload',
        task_names,
        batch=100,
    )
    return_code = maybe_failure[0].return_code if maybe_failure else 0

  return return_code


def workload_delete(args) -> None:
  """Function around workload delete.

  Args:
    args: user provided arguments for running the command.

  Returns:
    0 if successful and 1 otherwise.
  """
  if should_validate_dependencies(args):
    validate_dependencies_list(
        args, [SystemDependency.KUBECTL, SystemDependency.GCLOUD]
    )
  xpk_print('Starting Workload delete', flush=True)
  add_zone_and_project(args)
  get_cluster_credentials(args)

  will_delete = True
  if not args.workload:
    xpk_print('Get the name of the workloads in the cluster.')
    return_code, return_value = get_workload_list(args)

    if return_code != 0:
      xpk_print(f'List Job request returned ERROR {return_code}')
      xpk_exit(return_code)
    # Skip the header
    workloads = [x.split(' ')[0] for x in return_value.splitlines()][1:]
    if workloads:
      will_delete = ask_for_user_consent(
          f'Planning to delete {len(workloads)} workloads in the cluster'
          f' {args.cluster} including {workloads}. \nDo you wish to delete?'
      )
  else:
    workloads = [args.workload]

  if not workloads:
    xpk_print(
        'There are no workloads to delete matching the filter in the cluster.'
    )
  elif not will_delete:
    xpk_print('Skipping delete command.')
  else:
    return_code = delete_workloads(args, workloads)
    if return_code != 0:
      xpk_print(f'Delete Workload request returned ERROR {return_code}')
      xpk_exit(return_code)
  xpk_exit(0)


def workload_list(args) -> None:
  """Function around workload list.

  Args:
    args: user provided arguments for running the command.

  Returns:
    0 if successful and 1 otherwise.
  """
  if should_validate_dependencies(args):
    validate_dependencies_list(
        args, [SystemDependency.KUBECTL, SystemDependency.GCLOUD]
    )
  xpk_print('Starting workload list', flush=True)
  add_zone_and_project(args)
  get_cluster_credentials(args)

  if args.wait_for_job_completion:
    return_code = wait_for_job_completion(args)
    if return_code != 0:
      xpk_print(f'Wait for job completion returned ERROR {return_code}')
      xpk_exit(return_code)
    args.filter_by_job = args.wait_for_job_completion

  return_code, return_value = get_workload_list(args)

  if return_code != 0:
    xpk_print(f'List Job request returned ERROR {return_code}')
    xpk_exit(return_code)
  xpk_print(f'Workload List Output:\n{return_value}')

  workload_list_gcp_link = get_jobsets_list_gcp_link(project=args.project)
  xpk_print(f'See your workloads in Cloud Console: {workload_list_gcp_link}')

  xpk_exit(0)


# ---------------------------------------------------------------------------
# workload status — PoC queue health diagnostic
# ---------------------------------------------------------------------------

def workload_status(args) -> None:
  """Show PoC Kueue queue status for a workload or an entire team namespace.

  Tells the user if their workload is running, queued normally, or stuck,
  and provides a plain-English diagnosis with fix instructions.

  Args:
    args: user provided arguments (--cluster, --team, --workload).
  """
  import json as _json
  from datetime import datetime, timezone

  import subprocess as _subprocess

  if should_validate_dependencies(args):
    validate_dependencies_list(
        args, [SystemDependency.KUBECTL, SystemDependency.GCLOUD]
    )

  # Fill project from gcloud config if not provided.
  if not getattr(args, 'project', None):
    r = _subprocess.run(
        ['gcloud', 'config', 'get', 'project'], capture_output=True, text=True
    )
    args.project = r.stdout.strip().splitlines()[-1] if r.returncode == 0 else ''
  if not args.project:
    xpk_print('ERROR: --project not set and could not be determined from gcloud config.')
    xpk_exit(1)

  # Look up the cluster location directly — avoids requiring compute/zone in
  # gcloud config (which get_cluster_credentials needs but users often lack).
  if not getattr(args, 'zone', None):
    rc, loc = run_command_for_value(
        f'gcloud container clusters list --project={args.project}'
        f' --filter=name={args.cluster} --format="value(location)"',
        task='Find cluster location',
        quiet=True,
    )
    if rc != 0 or not loc.strip():
      xpk_print(f'ERROR: Could not find cluster "{args.cluster}" in project {args.project}.')
      xpk_exit(1)
    args.zone = loc.strip()

  get_cluster_credentials(args)

  team = args.team
  namespace, _lq, _pc = _resolve_poc_team(args)
  cq_name = namespace  # ClusterQueue name matches namespace name

  # ------------------------------------------------------------------
  # Internal helpers (no --context needed; xpk sets up kubeconfig)
  # ------------------------------------------------------------------

  def _kube_json(*kubectl_args):
    cmd = 'kubectl ' + ' '.join(kubectl_args) + ' -o json'
    rc, out = run_command_for_value(cmd, task=cmd, quiet=True)
    if rc != 0 or not out:
      return None
    try:
      return _json.loads(out)
    except _json.JSONDecodeError:
      return None

  def _events_text(ns, name):
    cmd = (
        f'kubectl get events -n {ns}'
        f' --field-selector involvedObject.name={name}'
        f' --sort-by=.lastTimestamp'
    )
    rc, out = run_command_for_value(cmd, task='get events', quiet=True)
    return out.strip() if rc == 0 else ''

  def _age(ts_str):
    if not ts_str:
      return '?'
    ts = datetime.fromisoformat(ts_str.replace('Z', '+00:00'))
    s = int((datetime.now(timezone.utc) - ts).total_seconds())
    if s < 60:
      return f'{s}s'
    if s < 3600:
      return f'{s // 60}m'
    return f'{s // 3600}h{(s % 3600) // 60}m'

  def _cond(wl, ctype):
    for c in wl.get('status', {}).get('conditions', []):
      if c.get('type') == ctype:
        return c
    return None

  def _is_true(c):
    return c is not None and c.get('status') == 'True'

  def _cq_chips(cq, section):
    total = 0
    for flavor in cq.get('status', {}).get(section, []):
      for res in flavor.get('resources', []):
        if res.get('name') == 'google.com/tpu':
          total += int(res.get('total', 0))
    return total

  def _cq_quota(cq):
    nominal, borrow = 0, 0
    for rg in cq.get('spec', {}).get('resourceGroups', []):
      for flavor in rg.get('flavors', []):
        for res in flavor.get('resources', []):
          if res.get('name') == 'google.com/tpu':
            nominal += int(res.get('nominalQuota', 0))
            b = res.get('borrowingLimit')
            if b is not None:
              borrow += int(b)
    return nominal, borrow

  def _ordinal(n):
    return f"{n}{['th','st','nd','rd','th'][min(n % 10, 4) if n % 100 not in (11,12,13) else 0]}"

  def _xpk_name_of(wl):
    name = wl['metadata'].get('labels', {}).get('xpk.google.com/workload')
    if name:
      return name
    for ref in wl['metadata'].get('ownerReferences', []):
      if ref.get('kind') in ('JobSet', 'Job'):
        return ref.get('name', '')
    n = wl['metadata']['name']
    if n.startswith('jobset-'):
      n = n[len('jobset-'):]
    if len(n) > 6 and n[-6] == '-':
      n = n[:-6]
    return n

  def _print_cq_summary(cq):
    if not cq:
      return
    st = cq.get('status', {})
    nominal, borrow_limit = _cq_quota(cq)
    running_chips  = _cq_chips(cq, 'flavorsUsage')
    reserved_chips = _cq_chips(cq, 'flavorsReservation')
    admitted   = st.get('admittedWorkloads', 0)
    reserving  = st.get('reservingWorkloads', 0)
    pending    = st.get('pendingWorkloads', 0)
    xpk_print(f'  Quota   : {nominal} chips nominal  +{borrow_limit} borrow  ='
              f' {nominal + borrow_limit} max')
    if reserved_chips > 0 and reserved_chips != running_chips:
      xpk_print(f'  Reserved: {reserved_chips} chips'
                f' ({reserving} workload(s) — quota held, awaiting admission)')
    xpk_print(f'  Running : {running_chips} chips ({admitted} workload(s) admitted)')
    xpk_print(f'  Queued  : {pending} workload(s) waiting for quota')

  def _diagnose_one(wl, all_items, cq):
    kueue_name = wl['metadata']['name']
    xpk_name   = _xpk_name_of(wl)
    created_at = wl['metadata']['creationTimestamp']

    cond_reserved = _cond(wl, 'QuotaReserved')
    cond_admitted = _cond(wl, 'Admitted')
    cond_finished = _cond(wl, 'Finished')

    is_admitted = _is_true(cond_admitted)
    is_reserved = _is_true(cond_reserved)
    is_finished = _is_true(cond_finished)
    finish_reason = cond_finished.get('reason', '') if cond_finished else ''

    xpk_print(f'Workload : {xpk_name}  ->  {kueue_name}')
    xpk_print(f'Age      : {_age(created_at)}')

    if is_finished:
      status_word = 'success' if finish_reason == 'Succeeded' else finish_reason
      xpk_print(f'Status   : FINISHED ({status_word})')
      msg = (cond_finished or {}).get('message', '')
      if msg:
        xpk_print(f'           {msg}')
      xpk_print('')
      return

    if is_admitted:
      admitted_ts = (cond_admitted or {}).get('lastTransitionTime', '')
      xpk_print(f'Status   : RUNNING  (admitted {_age(admitted_ts)} ago)')
      xpk_print(f'Team quota ({cq_name}):')
      _print_cq_summary(cq)
      xpk_print('')
      return

    if is_reserved:
      reserved_ts = (cond_reserved or {}).get('lastTransitionTime', '')
      xpk_print(f'Status   : STUCK — quota reserved but not admitted ({_age(reserved_ts)} ago)')
      xpk_print(f'Team quota ({cq_name}):')
      _print_cq_summary(cq)
      events = _events_text(namespace, kueue_name)
      warn = [l for l in events.splitlines()
              if any(w in l for w in ('Warning', 'Error', 'Failed', 'error', 'failed'))]
      if warn:
        xpk_print('Diagnosis: AdmissionCheck failed. Error(s):')
        for line in warn[-3:]:
          xpk_print(f'  {line.strip()}')
        if 'more than 49 characters' in events:
          import re
          m = re.search(r'"([^"]*-slice-job-\d+)"', events)
          max_len = 23 - len(namespace)
          xpk_print(f'')
          xpk_print(f'  Fix: --workload name "{xpk_name}" ({len(xpk_name)} chars)'
                    f' exceeds the {max_len}-char limit for {namespace}.')
          xpk_print(f'       Delete the JobSet and resubmit with a name <= {max_len} chars.')
          xpk_print(f'       Example: {xpk_name[:max_len]}')
      else:
        xpk_print('Diagnosis: AdmissionCheck still processing (no errors yet).')
        xpk_print(f'  kubectl describe workload {kueue_name} -n {namespace}')
      xpk_print('')
      return

    # Queued — compute position
    my_ts  = created_at
    my_pri = wl.get('spec', {}).get('priority') or 0
    ahead = []
    for other in all_items:
      oname = other['metadata']['name']
      if oname == kueue_name:
        continue
      if _is_true(_cond(other, 'Admitted')) or _is_true(_cond(other, 'Finished')):
        continue
      if _is_true(_cond(other, 'QuotaReserved')):
        continue
      other_ts  = other['metadata']['creationTimestamp']
      other_pri = other.get('spec', {}).get('priority') or 0
      if other_pri > my_pri or (other_pri == my_pri and other_ts < my_ts):
        ahead.append(_xpk_name_of(other))

    pos = len(ahead) + 1
    xpk_print(f'Status   : QUEUED — waiting for quota')
    if ahead:
      sample = ', '.join(ahead[:3]) + ('...' if len(ahead) > 3 else '')
      xpk_print(f'Position : {_ordinal(pos)} in line  ({len(ahead)} workload(s) ahead: {sample})')
    else:
      xpk_print(f'Position : {_ordinal(pos)} in line  (nothing ahead of you in this queue)')
    xpk_print(f'Team quota ({cq_name}):')
    _print_cq_summary(cq)

    # Anomaly detection
    st = (cq or {}).get('status', {})
    nominal, _ = _cq_quota(cq) if cq else (0, 0)
    running = _cq_chips(cq, 'flavorsUsage') if cq else 0
    if pos == 1 and st.get('admittedWorkloads', 0) == 0 and running == 0 and nominal > 0:
      xpk_print('Diagnosis: You\'re 1st in line with quota available but nothing running.')
      xpk_print(f'  This is unusual. Check: kubectl describe workload {kueue_name} -n {namespace}')
    elif pos == 1 and nominal > 0 and running < nominal * 0.9:
      xpk_print(f'Diagnosis: You\'re 1st in line and quota is not full — should be admitted soon.')
      xpk_print(f'  If still queued in a few minutes, check:')
      xpk_print(f'  kubectl describe workload {kueue_name} -n {namespace}')
    else:
      xpk_print('Diagnosis: Things look normal — waiting behind other workloads.')
    xpk_print('')

  # ------------------------------------------------------------------
  # Fetch data and run diagnostics
  # ------------------------------------------------------------------
  cq = _kube_json('get', 'clusterqueue', cq_name)
  all_wl_data = _kube_json('get', 'workload', '-n', namespace)
  all_items = all_wl_data.get('items', []) if all_wl_data else []

  if args.workload:
    prefix = f'jobset-{args.workload}-'
    matches = [i for i in all_items if i['metadata']['name'].startswith(prefix)]
    if not matches:
      xpk_print(f'No workload found matching "{prefix}*" in {namespace}')
      xpk_exit(1)
    if len(matches) > 1:
      names = [i['metadata']['name'] for i in matches]
      xpk_print(f'Multiple matches: {names}. Use the full Kueue name with --workload.')
      xpk_exit(1)
    _diagnose_one(matches[0], all_items, cq)
  else:
    if not all_items:
      xpk_print(f'No workloads in {namespace} — queue is empty.')
      xpk_print(f'Team quota ({cq_name}):')
      if cq:
        nominal, borrow = _cq_quota(cq)
        xpk_print(f'  Quota: {nominal} chips nominal  +{borrow} borrow  = {nominal + borrow} max')
      xpk_exit(0)

    def _sort_key(i):
      return (0 if _is_true(_cond(i, 'Admitted')) else 1,
              i['metadata']['creationTimestamp'])

    for item in sorted(all_items, key=_sort_key):
      _diagnose_one(item, all_items, cq)

  xpk_exit(0)
