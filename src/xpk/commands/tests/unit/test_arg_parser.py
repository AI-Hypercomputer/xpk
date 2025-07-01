import unittest
from ...cluster import parse_command_args_to_dict

class TestParseCommandArgsToDict(unittest.TestCase):

  def test_empty_string(self):
    self.assertEqual(parse_command_args_to_dict(''), {})

  def test_simple_key_value_pairs(self):
    result = parse_command_args_to_dict('--key1=value1 --key2=value2')
    self.assertEqual(result, {'--key1': 'value1', '--key2': 'value2'})

  def test_flag_with_space_value(self):
    result = parse_command_args_to_dict('--key1 value1 --key2 value2')
    self.assertEqual(result, {'--key1': 'value1', '--key2': 'value2'})

  def test_boolean_flags(self):
    result = parse_command_args_to_dict('--enable-feature --no-logs')
    self.assertEqual(result, {'--enable-feature': True, '--no-logs': True})

  def test_mixed_formats(self):
    result = parse_command_args_to_dict('--project=my-project --zone us-central1 --dry-run')
    self.assertEqual(result, {'--project': 'my-project', '--zone': 'us-central1', '--dry-run': True})

  def test_quoted_values(self):
    result = parse_command_args_to_dict('--description "My cluster with spaces" --name=test-cluster')
    self.assertEqual(result, {'--description': 'My cluster with spaces', '--name': 'test-cluster'})

  def test_no_double_hyphen_flags(self):
    result = parse_command_args_to_dict('random-word -f --flag')
    self.assertEqual(result, {'--flag': True}) # Only --flag should be parsed

  def test_duplicate_keys_last_one_wins(self):
    result = parse_command_args_to_dict('--key=value1 --key=value2')
    self.assertEqual(result, {'--key': 'value2'})

  def test_hyphenated_keys(self):
    result = parse_command_args_to_dict('--api-endpoint=some-url')
    self.assertEqual(result, {'--api-endpoint': 'some-url'})

if __name__ == '__main__':
  # Run python3 -m src.xpk.commands.tests.unit.test_arg_parser under the xpk folder.
  unittest.main()