import unittest
from ...cluster import process_gcloud_args

class TestProcessGcloudArgs(unittest.TestCase):

  def test_add_new_argument(self):
    final_args = {'--existing-key': 'existing-value'}
    user_args = {'--new-key': 'new-value'}
    process_gcloud_args(user_args, final_args)
    self.assertEqual(final_args, {'--existing-key': 'existing-value', '--new-key': 'new-value'})

  def test_override_existing_argument(self):
    final_args = {'--common-key': 'old-value'}
    user_args = {'--common-key': 'new-value'}
    process_gcloud_args(user_args, final_args)
    self.assertEqual(final_args, {'--common-key': 'new-value'})

  def test_no_enable_flag_overrides_enable(self):
    final_args = {'--enable-logging': True}
    user_args = {'--no-enable-logging': True}
    process_gcloud_args(user_args, final_args)
    self.assertEqual(final_args, {'--no-enable-logging': True})
    self.assertNotIn('--enable-logging', final_args) 

  def test_enable_flag_overrides_no_enable(self):
    final_args = {'--no-enable-monitoring': True}
    user_args = {'--enable-monitoring': True}
    process_gcloud_args(user_args, final_args)
    self.assertEqual(final_args, {'--enable-monitoring': True})
    self.assertNotIn('--no-enable-monitoring', final_args) 

  def test_no_conflict(self):
    final_args = {'--param1': 'value1'}
    user_args = {'--param2': 'value2'}
    process_gcloud_args(user_args, final_args)
    self.assertEqual(final_args, {'--param1': 'value1', '--param2': 'value2'})

  def test_empty_user_args(self):
    final_args = {'--param1': 'value1'}
    user_args = {}
    process_gcloud_args(user_args, final_args)
    self.assertEqual(final_args, {'--param1': 'value1'})

  def test_complex_overrides(self):
    final_args = {
        '--zone': 'us-east1-b',
        '--enable-ip-alias': True,
        '--machine-type': 'n1-standard-4',
        '--no-enable-public-ip': True # This will be removed if --enable-public-ip is set
    }
    user_args = {
        '--zone': 'us-central1-a', # Overrides
        '--no-enable-ip-alias': True,      # Overrides --enable-ip-alias
        '--disk-size': '200GB',     # New
        '--enable-public-ip': True # Overrides --no-enable-public-ip
    }
    process_gcloud_args(user_args, final_args)
    self.assertEqual(final_args, {
        '--zone': 'us-central1-a',
        '--no-enable-ip-alias': True,
        '--machine-type': 'n1-standard-4', # Not affected
        '--disk-size': '200GB',
        '--enable-public-ip': True
    })
    self.assertNotIn('--enable-ip-alias', final_args)
    self.assertNotIn('--no-enable-public-ip', final_args)

if __name__ == '__main__':
  # Run python3 -m src.xpk.commands.tests.unit.test_gcloud_arg_processor under the xpk folder.
  unittest.main()
