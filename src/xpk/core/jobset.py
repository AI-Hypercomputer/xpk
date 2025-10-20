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

import math

from ..utils.console import xpk_exit, xpk_print
from ..utils.file import write_tmp_file
from ..core.kueue_manager import (
    MEMORY_SIZE_PER_VM,
    MIN_MEMORY_LIMIT_SIZE,
)
from .commands import (
    run_command_for_value,
    run_command_with_updates_retry,
)

jobset_controller_manager_yml = """
apiVersion: apps/v1
kind: Deployment
metadata:
  labels:
    app.kubernetes.io/component: manager
    app.kubernetes.io/created-by: jobset
    app.kubernetes.io/instance: controller-manager
    app.kubernetes.io/managed-by: kustomize
    app.kubernetes.io/name: deployment
    app.kubernetes.io/part-of: jobset
    control-plane: controller-manager
  name: jobset-controller-manager
  namespace: jobset-system
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
        control-plane: controller-manager
    spec:
      containers:
      - args:
        - --config=/controller_manager_config.yaml
        - --zap-log-level=2
        command:
        - /manager
        image: registry.k8s.io/jobset/jobset:v0.8.0
        livenessProbe:
          httpGet:
            path: /healthz
            port: 8081
          initialDelaySeconds: 15
          periodSeconds: 20
        name: manager
        ports:
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
            memory: {memory_limit_size}
          requests:
            cpu: 1000m
            memory: 128Mi
        securityContext:
          allowPrivilegeEscalation: false
          capabilities:
            drop:
            - ALL
        volumeMounts:
        - mountPath: /controller_manager_config.yaml
          name: manager-config
          subPath: controller_manager_config.yaml
        - mountPath: /tmp/k8s-webhook-server/serving-certs
          name: cert
          readOnly: true
      securityContext:
        runAsNonRoot: true
      serviceAccountName: jobset-controller-manager
      terminationGracePeriodSeconds: 10
      volumes:
      - configMap:
          name: jobset-manager-config
        name: manager-config
      - name: cert
        secret:
          defaultMode: 420
          secretName: jobset-webhook-server-cert
"""


def update_jobset_resources_if_necessary():
  """Update the jobset manifest to increase the resources for the jobset controller manager.

  Returns:
    0 if successful and 1 otherwise.
  """
  # Get total number of nodes
  cmd_total_node_num = 'kubectl get node --no-headers | wc -l'
  return_code, out = run_command_for_value(
      cmd_total_node_num, 'Count total nodes'
  )
  if return_code != 0:
    xpk_exit(1)
  # 1.2MiB per VM or 4GiB (whichever is greater).
  new_memory_limit = (
      f'{max(math.ceil(int(out) * MEMORY_SIZE_PER_VM), MIN_MEMORY_LIMIT_SIZE)}Mi'
  )
  yml_string = jobset_controller_manager_yml.format(
      memory_limit_size=new_memory_limit,
  )
  tmp = write_tmp_file(yml_string)
  command = f'kubectl apply -f {str(tmp)}'

  task = 'Updating jobset Controller Manager resources'
  return_code = run_command_with_updates_retry(command, task)
  if return_code != 0:
    xpk_print(f'{task} returned ERROR {return_code}')
  return return_code
