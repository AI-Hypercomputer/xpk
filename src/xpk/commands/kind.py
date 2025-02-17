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

from ..core.commands import (
    run_command_for_value,
    run_command_with_updates,
)
from ..core.cluster import set_jobset_on_cluster, setup_k8s_env
from ..core.kjob import (
    verify_kjob_installed,
    prepare_kjob,
    apply_kjob_crds,
)
from ..core.kueue import (
    install_kueue_on_cluster,
    install_kueue_crs,
    wait_for_kueue_available,
)
from ..core.storage import install_storage_crd
from ..core.system_characteristics import (
    SystemCharacteristics,
    AcceleratorType,
)
from ..utils.console import (xpk_exit, xpk_print)


def cluster_create(args) -> None:
  """Function around cluster creation.

  Args:
    args: user provided arguments for running the command.

  Returns:
    0 if successful and 1 otherwise.
  """
  xpk_print(f'Starting cluster create for cluster {args.cluster}:', flush=True)

  create_cluster_command_code = create_cluster_if_necessary(args)
  if create_cluster_command_code != 0:
    xpk_exit(create_cluster_command_code)

  set_cluster_command_code = set_local_cluster_command(args)
  if set_cluster_command_code != 0:
    xpk_exit(set_cluster_command_code)

  xpk_print(
      'Enabling the jobset API on our cluster, to be deprecated when Jobset is'
      ' globally available'
  )
  set_jobset_on_cluster_code = set_jobset_on_cluster(args)
  if set_jobset_on_cluster_code != 0:
    xpk_exit(set_jobset_on_cluster_code)

  xpk_print('Enabling Kueue on the cluster')
  install_kueue_on_cluster_code = install_kueue_on_cluster(args)
  if install_kueue_on_cluster_code != 0:
    xpk_exit(install_kueue_on_cluster_code)

  xpk_print('Verifying kjob installation')
  err_code = verify_kjob_installed(args)
  if err_code > 0:
    xpk_exit(err_code)

  xpk_print('Applying kjob CDRs')
  err_code = apply_kjob_crds(args)
  if err_code > 0:
    xpk_exit(err_code)

  args.kind_cluster = True
  err_code = prepare_kjob(args)
  if err_code > 0:
    xpk_exit(err_code)

  k8s_client = setup_k8s_env(args)
  install_storage_crd(k8s_client)

  xpk_print('Wait for Kueue to be fully available')
  wait_for_kueue_available_code = wait_for_kueue_available(args)
  if wait_for_kueue_available_code != 0:
    xpk_exit(wait_for_kueue_available_code)

  args.num_slices = 1
  args.enable_pathways = False
  system = SystemCharacteristics(
      'N/A',
      1,
      'N/A',
      'N/A',
      1,
      AcceleratorType['CPU'],
      'kind',
  )

  xpk_print('Install Kueue Custom Resources')
  enable_kueue_credentials_code = install_kueue_crs(args, system, None)
  if enable_kueue_credentials_code != 0:
    xpk_exit(enable_kueue_credentials_code)

  xpk_print('Kind commands done! Resources are created.')
  xpk_exit(0)


def cluster_delete(args) -> None:
  """Function around cluster delete.

  Args:
    args: user provided arguments for running the command.

  Returns:
    0 if successful and 1 otherwise.
  """
  xpk_print(f'Starting cluster delete for cluster: {args.cluster}', flush=True)

  run_kind_cluster_delete_command_code = run_kind_cluster_delete_command(args)
  if run_kind_cluster_delete_command_code != 0:
    xpk_exit(run_kind_cluster_delete_command_code)
  xpk_print(f'Kind commands done! Cluster {args.cluster} deleted.')
  xpk_exit(0)


def cluster_list(args) -> None:
  """Function around cluster list.

  Args:
    args: user provided arguments for running the command.

  Returns:
    0 if successful and 1 otherwise.
  """
  if run_kind_clusters_list_command(args):
    xpk_exit(1)
  xpk_exit(0)


def create_cluster_if_necessary(args) -> int:
  """Creates cluster if not present in the project.

  Args:
    args: user provided arguments for running the command.

  Returns:
    0 if successful and 1 otherwise.
  """
  all_clusters, return_code = get_all_local_clusters_programmatic(args)
  if return_code > 0:
    xpk_print('Listing all clusters failed!')
    return 1
  if args.cluster in all_clusters:
    xpk_print('Skipping cluster creation since it already exists.')
    return 0
  else:
    return run_kind_cluster_create_command(args)


def run_kind_cluster_delete_command(args) -> int:
  """Run the Delete Kind Cluster request.

  Args:
    args: user provided arguments for running the command.

  Returns:
    0 if successful and 1 otherwise.
  """
  command = 'kind delete cluster'

  if args.cluster:
    command += f' --name={args.cluster}'

  return_code = run_command_with_updates(command, 'Cluster Delete', args)
  if return_code != 0:
    xpk_print(f'Cluster delete request returned ERROR {return_code}')
    return 1

  return 0


def run_kind_clusters_list_command(args) -> int:
  """List Kind Clusters within the project and location.

  Args:
    args: user provided arguments for running the command.

  Returns:
    0 if successful and 1 otherwise.
  """
  command = 'kind get clusters'
  return_code = run_command_with_updates(command, 'Cluster List', args)
  if return_code != 0:
    xpk_print(f'Cluster list request returned ERROR {return_code}')
    return 1

  return 0


def run_kind_cluster_create_command(args) -> int:
  """Run the Create Kind Cluster request.

  Args:
    args: user provided arguments for running the command.

  Returns:
    0 if successful and 1 otherwise.
  """
  command = 'kind create cluster'

  if args.cluster:
    command += f' --name={args.cluster}'

  if args.k8s_version:
    command += f' --image=kindest/node:v{args.k8s_version}'

  return_code = run_command_with_updates(command, 'Kind Cluster Create', args)
  if return_code != 0:
    xpk_print(f'GKE Cluster Create request returned ERROR {return_code}')
    return 1
  return 0


def get_all_local_clusters_programmatic(args) -> tuple[list[str], int]:
  """Gets all the local clusters.

  Args:
    args: user provided arguments for running the command.

  Returns:
    List of cluster names and 0 if successful and 1 otherwise.
  """
  command = 'kind get clusters'
  return_code, raw_cluster_output = run_command_for_value(
      command, 'Find if Cluster Exists', args
  )
  if return_code != 0:
    xpk_print(f'Find if Cluster Exists returned ERROR {return_code}')
    return [], return_code

  return raw_cluster_output.splitlines(), 0


def set_local_cluster_command(args) -> int:
  """Run local cluster configuration command to set the kubectl config.

  Args:
    args: user provided arguments for running the command.

  Returns:
    0 if successful and 1 otherwise.
  """
  if not args.cluster:
    command = 'kubectl config current-context'
    return_code, current_context = run_command_for_value(
        command, 'get current-context', args
    )
    xpk_print(
        'No local cluster name specified. Using current-context'
        f' `{current_context.strip()}`'
    )
    return return_code

  command = (
      f'kubectl config use-context kind-{args.cluster} --namespace=default'
  )
  task = f'switch to cluster {args.cluster}'
  return_code = run_command_with_updates(
      command,
      task,
      args,
  )
  if return_code != 0:
    xpk_print(f'{task} returned ERROR {return_code}')
  return return_code
