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

from argparse import Namespace

import math
import packaging
from packaging.version import Version

from ..utils.console import xpk_exit, xpk_print
from ..utils.file import write_tmp_file
from .capacity import B200_DEVICE_TYPE, H100_MEGA_DEVICE_TYPE, H200_DEVICE_TYPE
from .commands import (
    run_command_for_value,
    run_command_with_updates,
    run_command_with_updates_retry,
)
from .pathways import add_pw_resource_flavors, add_pw_resources_to_kueue
from .resources import AutoprovisioningConfig
from .scheduling import (
    create_accelerator_label,
    create_machine_label,
    get_total_chips_requested_from_args,
)
from .system_characteristics import (
    AcceleratorTypeToAcceleratorCharacteristics,
    SystemCharacteristics,
)

KUEUE_VERSION = 'v0.12.2'
CLUSTER_QUEUE_NAME = 'cluster-queue'
LOCAL_QUEUE_NAME = 'multislice-queue'
WAIT_FOR_KUEUE_TIMEOUT = '10m'
MEMORY_SIZE_PER_VM = 1.2
MIN_MEMORY_LIMIT_SIZE = 4096

packaging.version.VERSION_PATTERN = r'^v\d+\.\d+\.\d+$'

topology_yaml = """apiVersion: kueue.x-k8s.io/v1alpha1
kind: Topology
metadata:
  name: "gke-default"
spec:
  levels:
  - nodeLabel: "cloud.google.com/gce-topology-block"
  - nodeLabel: "cloud.google.com/gce-topology-subblock"
  - nodeLabel: "cloud.google.com/gce-topology-host"
  - nodeLabel: "kubernetes.io/hostname"
---
"""

cluster_set_crd_yaml = """apiVersion: kueue.x-k8s.io/v1beta1
kind: ResourceFlavor
metadata:
  name: {cluster_hardware_name}
spec:
  nodeLabels:
    {accelerator_label}
    {machine_label}
  {topology_label}
---
apiVersion: kueue.x-k8s.io/v1beta1
kind: AdmissionCheck
metadata:
  name: dws-prov
spec:
  controllerName: kueue.x-k8s.io/provisioning-request
  parameters:
    apiGroup: kueue.x-k8s.io
    kind: ProvisioningRequestConfig
    name: dws-config
---
apiVersion: kueue.x-k8s.io/v1beta1
kind: ProvisioningRequestConfig
metadata:
  name: dws-config
spec:
  provisioningClassName: queued-provisioning.gke.io
  podSetUpdates:
    nodeSelector:
    - key: autoscaling.gke.io/provisioning-request
      valueFromProvisioningClassDetail: ResizeRequestName
  managedResources:
  - {managed_resource}
---
{pw_resource_flavors}
apiVersion: kueue.x-k8s.io/v1beta1
kind: ClusterQueue
metadata:
  name: {cluster_queue_name}
spec:
  preemption:
      reclaimWithinCohort: Never # Don't preempt other queues in the cohort.
      withinClusterQueue: LowerPriority
  namespaceSelector: {{}} # match all.
  resourceGroups:
  {covered_resources_config}
  {pw_resources_kueue}
  {admission_checks}
---
apiVersion: kueue.x-k8s.io/v1beta1
kind: LocalQueue
metadata:
  namespace: default
  name: {local_queue_name}
spec:
  clusterQueue: {cluster_queue_name}
---
apiVersion: scheduling.k8s.io/v1
kind: PriorityClass
metadata:
  name: very-low
value: 100
globalDefault: false
description: "Very Low"
---
apiVersion: scheduling.k8s.io/v1
kind: PriorityClass
metadata:
  name: low
value: 250
globalDefault: false
description: "Low"
---
apiVersion: scheduling.k8s.io/v1
kind: PriorityClass
metadata:
  name: medium
value: 500
globalDefault: false
description: "Medium"
---
apiVersion: scheduling.k8s.io/v1
kind: PriorityClass
metadata:
  name: high
value: 750
globalDefault: false
description: "High"
---
apiVersion: scheduling.k8s.io/v1
kind: PriorityClass
metadata:
  name: very-high
value: 1000
globalDefault: false
description: "Very High"
"""

cluster_preheat_yml = """
apiVersion: apps/v1
kind: DaemonSet
metadata:
  name: {cachekey}
  labels:
    k8s-app: {cachekey}
spec:
  selector:
    matchLabels:
      k8s-app: {cachekey}
  updateStrategy:
    type: RollingUpdate
  template:
    metadata:
      labels:
        name: {cachekey}
        k8s-app: {cachekey}
    spec:
      affinity:
        nodeAffinity:
          requiredDuringSchedulingIgnoredDuringExecution:
            nodeSelectorTerms:
            - matchExpressions:
              - key: {nodeSelectorKey}
                operator: Exists
      tolerations:
      - operator: "Exists"
      containers:
      - image: {image_name}
        name: {cachekey}
        command: [ "sleep", "inf" ]
"""

kueue_controller_manager_yml = """
apiVersion: apps/v1
kind: Deployment
metadata:
  labels:
    app.kubernetes.io/component: controller
    app.kubernetes.io/name: kueue
    control-plane: controller-manager
  name: kueue-controller-manager
  namespace: kueue-system
spec:
  replicas: 1
  selector:
    matchLabels:
      control-plane: controller-manager
  template:
    metadata:
      annotations:
        kubectl.kubernetes.io/default-container: manager
      labels:
        app.kubernetes.io/component: controller
        app.kubernetes.io/name: kueue
        control-plane: controller-manager
    spec:
      containers:
      - args:
        - --config=/controller_manager_config.yaml
        - --zap-log-level=2
        command:
        - /manager
        image: registry.k8s.io/kueue/kueue:{KUEUE_VERSION}
        imagePullPolicy: Always
        livenessProbe:
          httpGet:
            path: /healthz
            port: 8081
          initialDelaySeconds: 15
          periodSeconds: 20
        name: manager
        ports:
        - containerPort: 8082
          name: visibility
          protocol: TCP
        - containerPort: 9443
          name: webhook-server
          protocol: TCP
        readinessProbe:
          httpGet:
            path: /readyz
            port: 8081
          initialDelaySeconds: 5
          periodSeconds: 10
        resources:
          limits:
            cpu: 1000m
            memory: {memory_limit_size}
          requests:
            cpu: 1000m
            memory: 512Mi
        securityContext:
          allowPrivilegeEscalation: false
        volumeMounts:
        - mountPath: /visibility
          name: visibility
        - mountPath: /tmp/k8s-webhook-server/serving-certs
          name: cert
          readOnly: true
        - mountPath: /controller_manager_config.yaml
          name: manager-config
          subPath: controller_manager_config.yaml
      securityContext:
        runAsNonRoot: true
      serviceAccountName: kueue-controller-manager
      terminationGracePeriodSeconds: 10
      volumes:
      - name: visibility
        emptyDir: {{}}
      - name: cert
        secret:
          defaultMode: 420
          secretName: kueue-webhook-server-cert
      - configMap:
          name: kueue-manager-config
        name: manager-config
"""


def verify_kueuectl(args: Namespace) -> None:
  """Verify if kueuectl is installed.
  Args:
    args: user provided arguments.
  Returns:
    None
  """
  xpk_print('Veryfing kueuectl installation')

  command = 'kubectl kueue version'
  task = 'Verify kueuectl installation on cluster'
  verify_kueuectl_installed_code, _ = run_command_for_value(command, task, args)

  if verify_kueuectl_installed_code == 0:
    xpk_print('kueuectl found')

  if verify_kueuectl_installed_code != 0:
    xpk_print(
        'kueuectl not found. Please follow'
        ' https://kueue.sigs.k8s.io/docs/reference/kubectl-kueue/installation/'
        ' to install kueuectl.'
    )
    xpk_exit(verify_kueuectl_installed_code)


def delete_multikueueconfigs_definitions(args) -> int:
  command = 'kubectl delete crd multikueueconfigs.kueue.x-k8s.io'
  task = 'Delete multikueueconfigs crds'
  return_code = run_command_with_updates_retry(command, task, args)
  if return_code != 0:
    xpk_print(f'{task} returned ERROR {return_code}')
  return return_code


def delete_multikueueclusters_definitions(args) -> int:
  command = 'kubectl delete crd multikueueclusters.kueue.x-k8s.io'
  task = 'Delete multikueueclusters crds'
  return_code = run_command_with_updates_retry(command, task, args)
  if return_code != 0:
    xpk_print(f'{task} returned ERROR {return_code}')
  return return_code


def get_kueue_version(args) -> tuple[int, str]:
  command = 'kubectl kueue version'
  task = 'Get kueue version on server'
  return_code, val = run_command_for_value(command, task, args)
  if return_code != 0:
    return return_code, ''
  lines = val.splitlines()
  if len(lines) == 1:
    return 1, ''
  server_version_line = lines[1]
  manager_image_version = server_version_line.split(':')[-1]
  return return_code, manager_image_version


def install_kueue_on_cluster(args) -> int:
  """Install Kueue on the cluster.

  Args:
    args: user provided arguments for running the command.

  Returns:
    0 if successful and 1 otherwise.
  """

  err_code, kueue_version_installed = get_kueue_version(args)
  if err_code == 0:
    if Version(kueue_version_installed) < Version('v0.9.0') and Version(
        KUEUE_VERSION
    ) >= Version('v0.9.0'):
      xpk_print('Upgrading kueue on cluster from version < 0.9.0.')
      upgrade_code = delete_multikueueclusters_definitions(args)
      if upgrade_code != 0:
        return upgrade_code
      upgrade_code = delete_multikueueconfigs_definitions(args)
      if upgrade_code != 0:
        return upgrade_code

  command = (
      'kubectl apply --server-side --force-conflicts -f'
      f' https://github.com/kubernetes-sigs/kueue/releases/download/{KUEUE_VERSION}/manifests.yaml'
  )
  task = 'Set Kueue On Cluster'
  return_code = run_command_with_updates_retry(command, task, args)
  if return_code != 0:
    xpk_print(f'{task} returned ERROR {return_code}')
  return return_code


def wait_for_kueue_available(args: Namespace) -> int:
  """Wait for Kueue to be fully available.

  Args:
    args: user provided arguments for running the command.

  Returns:
    0 if successful and 1 otherwise.
  """
  command = (
      'kubectl wait deploy/kueue-controller-manager -nkueue-system'
      f' --for=condition=available --timeout={WAIT_FOR_KUEUE_TIMEOUT}'
  )
  task = 'Wait for Kueue to be available'
  return_code = run_command_with_updates(command, task, args)
  if return_code != 0:
    xpk_print(f'{task} returned ERROR {return_code}')
  return return_code


def install_kueue_crs(
    args,
    system: SystemCharacteristics,
    autoprovisioning_config: AutoprovisioningConfig | None,
    flex_with_tpu=False,
) -> int:
  """Install Kueue Custom Resources.

  Args:
    args: user provided arguments for running the command.
    system: system level arguments.
    autoprovisioning_config: Autoprovisioning config to configure kueue with if
        autoprovisioning is enabled.

  Returns:
    0 if successful and 1 otherwise.
  """
  device_type = system.device_type
  cluster_hardware_name = f'{args.num_slices}x{device_type}'
  resource_type = AcceleratorTypeToAcceleratorCharacteristics[
      system.accelerator_type
  ].resource_type

  autoprovisioning_enabled = False
  if autoprovisioning_config:
    # Determine total resources available based on autoprovisioning max chips.
    autoprovisioning_enabled = True
    total_chips = autoprovisioning_config.maximum_chips
    cluster_hardware_name = f'{system.gke_accelerator}'
  else:
    # Determine total chips based on user specified topology.
    total_chips = get_total_chips_requested_from_args(args, system)
  if args.flex and flex_with_tpu is False:
    admission_checks = """
  admissionChecks:
  - dws-prov
"""
  else:
    admission_checks = ''

  covered_resources_config = get_kueue_covered_resources_config(
      cluster_hardware_name=cluster_hardware_name,
      resource_type=resource_type,
      total_chips=total_chips,
      cpu_limit=args.cpu_limit,
      memory_limit=args.memory_limit,
  )
  topology_label = ''
  if system.device_type in [
      H100_MEGA_DEVICE_TYPE,
      H200_DEVICE_TYPE,
      B200_DEVICE_TYPE,
  ]:
    topology_label = 'topologyName: "gke-default"'
  res_type = AcceleratorTypeToAcceleratorCharacteristics[
      system.accelerator_type
  ].resource_type
  yml_string = cluster_set_crd_yaml.format(
      system=system,
      cluster_hardware_name=cluster_hardware_name,
      accelerator_label=create_accelerator_label(
          system.accelerator_type, system
      ),
      machine_label=create_machine_label(
          system.accelerator_type, system, autoprovisioning_enabled
      ),
      topology_label=topology_label,
      covered_resources_config=covered_resources_config,
      resource_type=res_type,
      pw_resource_flavors=add_pw_resource_flavors(args),
      pw_resources_kueue=add_pw_resources_to_kueue(args),
      admission_checks=admission_checks,
      managed_resource=res_type,
      cluster_queue_name=CLUSTER_QUEUE_NAME,
      local_queue_name=LOCAL_QUEUE_NAME,
  )
  if system.device_type in [
      H100_MEGA_DEVICE_TYPE,
      H200_DEVICE_TYPE,
      B200_DEVICE_TYPE,
  ]:
    yml_string = topology_yaml + yml_string

  tmp = write_tmp_file(yml_string)
  command = f'kubectl apply -f {str(tmp)}'

  task = 'Applying Kueue Custom Resources'
  return_code = run_command_with_updates_retry(command, task, args)
  if return_code != 0:
    xpk_print(f'{task} returned ERROR {return_code}')
  return return_code


def get_kueue_covered_resources_config(
    cluster_hardware_name, resource_type, total_chips, cpu_limit, memory_limit
) -> str:
  """Gets Kueue covered resources configuration.

  Args:
    cluster_hardware_name: cluster hardware name.
    resource_type: resource type of tpu or gpu.
    total_chips: total number of chips for the specific resource type.

  Returns:
    A string of Kueue covered resources configuration.
  """
  config_format = """
  - coveredResources: {resource_types}
    flavors:
    - name: {cluster_hardware_name}
      resources:
      - name: "{resource_type}"
        nominalQuota: {total_chips}"""
  resource_types = [resource_type]
  if cpu_limit:
    config_format = config_format + """
      - name: "cpu"
        nominalQuota: {cpu_limit}"""
    resource_types.append('cpu')
  if memory_limit:
    config_format = config_format + """
      - name: "memory"
        nominalQuota: {memory_limit}"""
    resource_types.append('memory')

  config_string = config_format.format(
      cluster_hardware_name=cluster_hardware_name,
      resource_types=resource_types,
      resource_type=resource_type,
      total_chips=total_chips,
      cpu_limit=cpu_limit,
      memory_limit=memory_limit,
  )
  return config_string


def update_kueue_resources_if_necessary(args):
  """Update the kueue manifest to increase the resources for the kueue controller manager.

  Args:
    args: user provided arguments for running the command.

  Returns:
    0 if successful and 1 otherwise.
  """
  # Get total number of nodes
  cmd_total_node_num = 'kubectl get node --no-headers | wc -l'
  return_code, out = run_command_for_value(
      cmd_total_node_num, 'Count total nodes', args
  )
  if return_code != 0:
    xpk_exit(1)
  # 1.2MiB per VM or 4GiB (whichever is greater).
  new_memory_limit = (
      f'{max(math.ceil(int(out) * MEMORY_SIZE_PER_VM), MIN_MEMORY_LIMIT_SIZE)}Mi'
  )
  yml_string = kueue_controller_manager_yml.format(
      memory_limit_size=new_memory_limit, KUEUE_VERSION=KUEUE_VERSION
  )
  tmp = write_tmp_file(yml_string)
  command = f'kubectl apply -f {str(tmp)}'

  task = 'Updating Kueue Controller Manager resources'
  return_code = run_command_with_updates_retry(command, task, args)
  if return_code != 0:
    xpk_print(f'{task} returned ERROR {return_code}')
  return return_code
