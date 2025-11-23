import unittest
from unittest import mock
import argparse
import os
from .workload import workload_create
from ..core.system_characteristics import SystemCharacteristics, AcceleratorType

class WorkloadOutputManifestTest(unittest.TestCase):
  def setUp(self):
    self.args = argparse.Namespace()
    self.args.workload = 'test-workload'
    self.args.cluster = 'test-cluster'
    self.args.project = 'test-project'
    self.args.zone = 'us-central1-a'
    self.args.tpu_type = 'v4-8'
    self.args.command = 'echo hello'
    self.args.output_manifest_file = 'test-manifest.yaml'
    self.args.use_pathways = False
    self.args.sub_slicing_topology = None
    self.args.scheduler = 'default-scheduler'
    self.args.docker_image_pull_secret = None
    self.args.priority = 'medium'
    self.args.termination_grace_period_seconds = 30
    self.args.num_slices = 1
    self.args.max_restarts = 0
    self.args.ttl_seconds_after_finished = 12 * 60 * 60
    self.args.docker_image = None
    self.args.base_docker_image = 'python:3.10'
    self.args.script_dir = '.'
    self.args.env_file = None
    self.args.env = None
    self.args.use_vertex_tensorboard = False
    self.args.debug_dump_gcs = None
    self.args.deploy_stacktrace_sidecar = False
    self.args.restart_on_exit_codes = None
    self.args.mtc_enabled = False
    self.args.ramdisk_directory = ''
    self.args.enable_debug_logs = False
    self.args.device_type = 'v4-8'
    self.args.dry_run = True
    self.args.output_dir = None
    self.args.docker_name = 'user-container'

  @mock.patch('xpk.commands.workload.get_system_characteristics')
  @mock.patch('xpk.commands.workload.check_if_workload_exists')
  @mock.patch('xpk.commands.workload.check_if_workload_can_schedule')
  @mock.patch('xpk.commands.workload.get_cluster_configmap')
  @mock.patch('xpk.commands.workload.xpk_print')
  @mock.patch('xpk.commands.workload.xpk_exit')
  @mock.patch('xpk.commands.workload.is_dry_run')
  @mock.patch('xpk.core.docker_resources.is_dry_run')
  @mock.patch('xpk.commands.workload.run_command_with_updates')
  @mock.patch('xpk.commands.workload.write_tmp_file')
  @mock.patch('xpk.commands.workload.get_user_workload_container')
  @mock.patch('xpk.commands.workload.get_cluster_location')
  def test_workload_create_dry_run_with_output_file(
      self,
      mock_get_cluster_location,
      mock_get_user_workload_container,
      mock_write_tmp_file,
      mock_run_command_with_updates,
      mock_docker_resources_is_dry_run,
      mock_workload_is_dry_run,
      mock_xpk_exit,
      mock_xpk_print,
      mock_get_cluster_configmap,
      mock_check_if_workload_can_schedule,
      mock_check_if_workload_exists,
      mock_get_system_characteristics,
  ):
    mock_get_system_characteristics.return_value = (SystemCharacteristics(
        accelerator_type=AcceleratorType.TPU,
        topology='2x2x1',
        chips_per_vm=4,
        vms_per_slice=1,
        device_type='v4-8',
        gke_accelerator='tpu-v4-podslice',
        gce_machine_type='ct4p-hightpu-4t',
        supports_sub_slicing=False
    ), 0)
    mock_check_if_workload_exists.return_value = False
    mock_check_if_workload_can_schedule.return_value = True
    mock_get_cluster_configmap.return_value = {'xpk_version': '0.1.0'}
    mock_write_tmp_file.return_value = 'tmp_file.yaml'
    mock_run_command_with_updates.return_value = 0
    mock_workload_is_dry_run.return_value = True
    mock_docker_resources_is_dry_run.return_value = True
    mock_get_user_workload_container.return_value = ('dummy_container_string', None)
    mock_get_cluster_location.return_value = 'us-central1-a'

    workload_create(self.args)

    # Check if file was created
    self.assertTrue(os.path.exists('test-manifest.yaml'))
    with open('test-manifest.yaml', 'r') as f:
      content = f.read()
      self.assertIn('kind: JobSet', content)
      self.assertIn('name: test-workload', content)
    
    # Check if run_command_with_updates was called (kubectl apply) - even in dry run it is called but returns 0
    mock_run_command_with_updates.assert_called()
    
    # Check if xpk_exit(0) was called
    mock_xpk_exit.assert_called_with(0)

    # Clean up
    if os.path.exists('test-manifest.yaml'):
      os.remove('test-manifest.yaml')

if __name__ == '__main__':
  unittest.main()
