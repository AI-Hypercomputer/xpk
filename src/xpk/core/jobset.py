import math

from ..utils.console import xpk_exit, xpk_print
from ..utils.file import write_tmp_file
from ..core.kueue import (
    MEMORY_SIZE_PER_VM,
    MIN_MEMORY_LIMIT_SIZE,
)
from .commands import (
    run_command_for_value,
    run_command_with_updates_retry,
)

jobset_controller_manager_yml = """
apiVersion: v1
kind: Service
metadata:
  labels:
    app.kubernetes.io/component: webhook
    app.kubernetes.io/created-by: jobset
    app.kubernetes.io/instance: webhook-service
    app.kubernetes.io/managed-by: kustomize
    app.kubernetes.io/name: service
    app.kubernetes.io/part-of: jobset
  name: jobset-webhook-service
  namespace: jobset-system
spec:
  ports:
  - port: 443
    protocol: TCP
    targetPort: 9443
  selector:
    control-plane: controller-manager
---
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
            cpu: 500m
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

def update_jobset_resources_if_necessary(args):
  """Update the jobset manifest to increase the resources for the jobset controller manager.

  Args:
    args: user provided arguments for running the command.

  Returns:
    0 if successful and 1 otherwise.
  """
  # Get total number of nodes
  cmd_total_node_num = (
      'kubectl get node --no-headers | wc -l'
  )
  return_code, out = run_command_for_value(
      cmd_total_node_num, 'Count total nodes', args
  )
  if return_code != 0:
    xpk_exit(1)
  # 1.2MiB per VM or 4GiB (whichever is greater).
  new_memory_limit = f"{max(math.ceil(int(out) * MEMORY_SIZE_PER_VM), MIN_MEMORY_LIMIT_SIZE)}Mi"
  yml_string = jobset_controller_manager_yml.format(
      memory_limit_size=new_memory_limit,
  )
  tmp = write_tmp_file(yml_string)
  command = f'kubectl apply -f {str(tmp.file.name)}'

  task = 'Updating jobset Controller Manager resources'
  return_code = run_command_with_updates_retry(command, task, args)
  if return_code != 0:
    xpk_print(f'{task} returned ERROR {return_code}')
  return return_code