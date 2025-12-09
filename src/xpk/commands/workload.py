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
from ..core.commands import run_command_with_updates, run_commands
from ..core.config import (VERTEX_TENSORBOARD_FEATURE_FLAG, XPK_CURRENT_VERSION)
from ..core.docker_container import (
    get_main_container_docker_image,
    get_user_workload_container,
)
from ..core.kueue_manager import LOCAL_QUEUE_NAME
from ..core.docker_resources import get_volumes, parse_env_config
from ..core.gcloud_context import add_zone_and_project
from ..core.monitoring import get_gke_outlier_dashboard
from ..core.nap import (
    get_autoprovisioning_node_selector_args,
    is_autoprovisioning_enabled,
)
from ..core.network import get_cluster_subnetworks
from ..core.pathways import (
    append_custom_colocated_python_sidecar,
    append_custom_pathways_proxy_server,
    append_custom_pathways_server,
    append_custom_pathways_worker,
    check_if_pathways_job_is_installed,
    ensure_pathways_workload_prerequisites,
    get_pathways_unified_query_link,
    get_user_workload_for_pathways,
    try_to_delete_pathwaysjob_first,
)
from ..core.resources import get_cluster_capacity_type, get_cluster_system_characteristics_from_config_map
from ..core.resources import ConfigMapType, get_cluster_configmap
from ..core.nodepool import ensure_resource_policy_exists
from ..core.scheduling import (
    WorkloadScheduling,
    check_if_workload_can_schedule,
    create_tpu_machine_type,
    create_tpu_topology,
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
from ..utils.validation import validate_dependencies_list, SystemDependency, should_validate_dependencies
from . import cluster_gcluster
from .common import is_TAS_possible
from jinja2 import Environment, FileSystemLoader
from ..utils.templates import get_templates_absolute_path

WORKLOAD_CREATE_YAML = """apiVersion: jobset.x-k8s.io/v1alpha2
kind: JobSet
metadata:
  name: {args.workload}
  labels:
    kueue.x-k8s.io/queue-name: {local_queue_name}  # Name of the LocalQueue
    xpk.google.com/workload: {args.workload}
  annotations:
    alpha.jobset.sigs.k8s.io/exclusive-topology: cloud.google.com/gke-nodepool # 1:1 job replica to node pool assignment
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
              annotations:
                {storage_annotations}
                {sub_slicing_annotations}
                {annotations_machine_label}
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
# The indentation of PW_WORKLOAD_CREATE_YAML is intentional to allow reusing the user workload container YAML.
PW_WORKLOAD_CREATE_YAML = """
    apiVersion: pathways-job.pathways.domain/v1
    kind: PathwaysJob
    metadata:
      name: {args.workload}
      labels:
        kueue.x-k8s.io/queue-name: {local_queue_name}  # Name of the LocalQueue
        xpk.google.com/workload: {args.workload}
    spec:
      maxRestarts: {args.max_restarts}
      customComponents:
      {custom_pathways_proxy_server}
      {custom_pathways_server}
      {custom_pathways_worker}
      {colocated_python_sidecar}
      workers:
      - type: {machine_type}
        topology: {topology}
        numSlices: {args.num_slices}
        maxSliceRestarts: {args.max_slice_restarts}
        terminationGracePeriodSeconds: {args.termination_grace_period_seconds}
        priorityClassName: {args.priority}
        nodeSelector:
          {placement_policy_label}
          {autoprovisioning_args}
      pathwaysDir: {args.pathways_gcs_location} #This bucket needs to be created in advance.
      controller:
        # #Pod template for training, default mode.
        deploymentMode: default
        mainContainerName: {args.docker_name}
        elasticSlices: {args.elastic_slices}
        template:
      {user_workload}
"""

ARM_GPU_WORKLOAD_CREATE_JINJA_FILE = 'arm_gpu_workload_crate.yaml.j2'


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
    validate_dependencies_list([
        SystemDependency.KUBECTL,
        SystemDependency.GCLOUD,
        SystemDependency.DOCKER,
    ])
  k8s_api_client = None
  if not is_dry_run():
    k8s_api_client = setup_k8s_env(args)
    setup_k8s_service_accounts()

  workload_exists = check_if_workload_exists(args)

  if workload_exists:
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
    for i in range(workload_system.parallel_containers):
      docker_image_sufix = (
          f'-{i + 1}' if workload_system.parallel_containers > 1 else ''
      )
      pod_failure_policy += f"""
            - action: FailJob
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

  # Create the workload file based on accelerator type or workload type.
  if workload_system.accelerator_type == AcceleratorType.GPU:
    container, debugging_dashboard_id = get_user_workload_container(
        args, workload_system
    )
    gpu_scheduler, return_code = get_gpu_scheduler(
        args, workload_system, autoprovisioning_args
    )
    if return_code != 0:
      xpk_exit(return_code)
    capacity_type = get_cluster_capacity_type(args)

    annotations = (
        (
            'kueue.x-k8s.io/podset-preferred-topology:'
            ' "cloud.google.com/gce-topology-host"'
        )
        if is_TAS_possible(cluster_system, capacity_type)
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
    yml_string = PW_WORKLOAD_CREATE_YAML.format(
        args=args,
        topology=create_tpu_topology(workload_system),
        machine_type=create_tpu_machine_type(workload_system),
        custom_pathways_proxy_server=append_custom_pathways_proxy_server(args),
        custom_pathways_server=append_custom_pathways_server(args),
        custom_pathways_worker=append_custom_pathways_worker(args),
        colocated_python_sidecar=append_custom_colocated_python_sidecar(args),
        user_workload=get_user_workload_for_pathways(args, workload_system),
        local_queue_name=LOCAL_QUEUE_NAME,
        autoprovisioning_args=autoprovisioning_args,
        placement_policy_label=placement_policy_label,
    )
  else:
    use_sub_slicing = (
        workload_scheduling == WorkloadScheduling.SUB_SLICING_AVAILABLE
    )
    use_super_slicing = (
        workload_scheduling == WorkloadScheduling.SUPER_SLICING_AVAILABLE
    )
    if use_sub_slicing:
      xpk_print('Workload will be scheduled using the Sub-slicing feature.')
    if use_super_slicing:
      xpk_print('Workload will be scheduled using the Super-slicing feature.')

    container, debugging_dashboard_id = get_user_workload_container(
        args, workload_system
    )

    machine_label = (
        create_machine_label(cluster_system)
        if use_sub_slicing and cluster_system
        else create_machine_label(workload_system)
    )
    node_selector_machine_label = machine_label if not use_super_slicing else ''
    annotations_machine_label = machine_label if use_super_slicing else ''

    yml_string = WORKLOAD_CREATE_YAML.format(
        args=args,
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
        annotations_machine_label=annotations_machine_label,
        local_queue_name=LOCAL_QUEUE_NAME,
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
        'Follow your Pathways workload and other resources here : '
        f'{get_pathways_unified_query_link(args)}'
    )
  else:
    xpk_print(
        'Follow your workload here:'
        # pylint: disable=line-too-long
        f' https://console.cloud.google.com/kubernetes/service/{get_cluster_location(args.project, args.cluster, args.zone)}/{args.cluster}/default/{args.workload}/details?project={args.project}'
    )
    duration_of_logs = 'P1D'  # Past 1 Day
    xpk_print(
        'Follow your worker 0, slice 0 logs here:'
        ' Adjust the pod name'
        ' ([prefix]-slice-job-[slice_number]-[worker_number])'
        ' after clicking the url if you want other worker logs.'
        # pylint: disable=line-too-long
        f' https://console.cloud.google.com/logs/query;query=resource.type%3D%22k8s_container%22%0Aresource.labels.project_id%3D%22{args.project}%22%0Aresource.labels.location%3D%22{get_cluster_location(args.project, args.cluster, args.zone)}%22%0Aresource.labels.cluster_name%3D%22{args.cluster}%22%0Aresource.labels.namespace_name%3D%22default%22%0Aresource.labels.pod_name:%22{args.workload}-slice-job-0-0-%22%20severity%3E%3DDEFAULT;storageScope=project;duration={duration_of_logs}?e=13802955&mods=allow_workbench_image_override&project={args.project}'
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


def workload_delete(args) -> None:
  """Function around workload delete.

  Args:
    args: user provided arguments for running the command.

  Returns:
    0 if successful and 1 otherwise.
  """
  if should_validate_dependencies(args):
    validate_dependencies_list(
        [SystemDependency.KUBECTL, SystemDependency.GCLOUD]
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
    # If PathwaysJob exists, delete it.
    if check_if_pathways_job_is_installed(
        args
    ) and try_to_delete_pathwaysjob_first(args, workloads):
      xpk_exit(0)
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
      return_code = (
          maybe_failure.return_code if maybe_failure is not None else 0
      )

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
        [SystemDependency.KUBECTL, SystemDependency.GCLOUD]
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
