"""Tests for precedence between config file values and command line arguments."""
import sys
import unittest
from unittest.mock import patch

from src.cli import DEFAULTS, args_to_dict, resolve_params
from src.utils.cli import parse_args
from src.utils.config import get_storage_config, merge_config_and_args


def parse_cli(argv):
    """Parse a simulated command line into the dict shape resolve_params expects."""
    with patch.object(sys, 'argv', ['docu-crawler'] + argv):
        return args_to_dict(parse_args())


class TestConfigFilePrecedence(unittest.TestCase):
    """A config file value must survive when the user omits the matching flag.

    These guard the defect where argparse's own defaults were mistaken for
    user-supplied values and silently overwrote the config file.
    """

    def test_single_file_from_config_survives_absent_flag(self):
        """Given single_file in config, when --single-file is omitted, it stays true."""
        config = {'single_file': True}

        params = resolve_params(config, parse_cli(['https://example.com']))

        self.assertTrue(params['single_file'])

    def test_frontmatter_from_config_survives_absent_flag(self):
        """Given frontmatter in config, when --frontmatter is omitted, it stays true."""
        config = {'frontmatter': True}

        params = resolve_params(config, parse_cli(['https://example.com']))

        self.assertTrue(params['frontmatter'])

    def test_storage_type_from_config_survives_absent_flag(self):
        """Given storage_type in config, when --storage-type is omitted, it is kept."""
        config = {'storage_type': 's3', 's3_bucket': 'my-bucket'}

        params = resolve_params(config, parse_cli(['https://example.com']))

        self.assertEqual(params['storage_type'], 's3')

    def test_sftp_port_from_config_survives_absent_flag(self):
        """Given sftp_port in config, when --sftp-port is omitted, it is kept."""
        config = {'storage_type': 'sftp', 'sftp_port': 2222}

        params = resolve_params(config, parse_cli(['https://example.com']))

        self.assertEqual(params['sftp_port'], 2222)

    def test_use_gcs_from_config_survives_absent_flag(self):
        """Given use_gcs in config, when --use-gcs is omitted, it is kept."""
        config = {'use_gcs': True, 'bucket': 'my-bucket'}

        params = resolve_params(config, parse_cli(['https://example.com']))

        self.assertTrue(params['use_gcs'])

    def test_config_values_reach_storage_config(self):
        """A config-only sftp setup must survive all the way into the storage config."""
        config = {'storage_type': 'sftp', 'sftp_host': 'sftp.example.com',
                  'sftp_user': 'crawler', 'sftp_port': 2222}

        params = resolve_params(config, parse_cli(['https://example.com']))
        storage_config = get_storage_config(params)

        self.assertEqual(storage_config['storage_type'], 'sftp')
        self.assertEqual(storage_config['sftp_port'], 2222)


class TestCommandLinePrecedence(unittest.TestCase):
    """An explicitly supplied argument must still win over the config file."""

    def test_single_file_flag_overrides_config(self):
        """Given single_file false in config, when --single-file is passed, it wins."""
        config = {'single_file': False}

        params = resolve_params(config, parse_cli(['https://example.com', '--single-file']))

        self.assertTrue(params['single_file'])

    def test_frontmatter_flag_overrides_config(self):
        """Given frontmatter false in config, when --frontmatter is passed, it wins."""
        config = {'frontmatter': False}

        params = resolve_params(config, parse_cli(['https://example.com', '--frontmatter']))

        self.assertTrue(params['frontmatter'])

    def test_output_argument_overrides_config(self):
        """Given output in config, when --output is passed, the argument wins."""
        config = {'output': '/from/config'}

        params = resolve_params(
            config, parse_cli(['https://example.com', '--output', '/from/cli'])
        )

        self.assertEqual(params['output'], '/from/cli')

    def test_storage_type_argument_overrides_config(self):
        """Given storage_type in config, when --storage-type is passed, it wins."""
        config = {'storage_type': 's3'}

        params = resolve_params(
            config, parse_cli(['https://example.com', '--storage-type', 'local'])
        )

        self.assertEqual(params['storage_type'], 'local')


class TestDefaultsFallback(unittest.TestCase):
    """DEFAULTS applies only when neither the config file nor the CLI supplies a value."""

    def test_defaults_used_when_nothing_supplied(self):
        """Given an empty config and a bare command line, DEFAULTS fill the gaps."""
        params = resolve_params({}, parse_cli(['https://example.com']))

        self.assertFalse(params['single_file'])
        self.assertFalse(params['frontmatter'])
        self.assertEqual(params['storage_type'], 'local')
        self.assertEqual(params['delay'], DEFAULTS['delay'])
        self.assertEqual(params['output'], DEFAULTS['output'])

    def test_sftp_port_has_a_default(self):
        """sftp_port must resolve to 22 rather than None when nobody supplies it."""
        params = resolve_params({}, parse_cli(['https://example.com']))

        self.assertEqual(params['sftp_port'], 22)

    def test_every_default_key_is_populated(self):
        """No DEFAULTS key may resolve to None, since downstream code indexes them."""
        params = resolve_params({}, parse_cli(['https://example.com']))

        unset = [key for key in DEFAULTS if params.get(key) is None and DEFAULTS[key] is not None]
        self.assertEqual(unset, [])


class TestMergeConfigAndArgs(unittest.TestCase):
    """Direct tests for the merge helper's contract."""

    def test_none_valued_arguments_do_not_override_config(self):
        """A None argument means 'not supplied' and must leave the config value alone."""
        result = merge_config_and_args({'delay': 5.0}, {'delay': None})

        self.assertEqual(result['delay'], 5.0)

    def test_supplied_arguments_override_config(self):
        """A non-None argument means 'supplied' and must win."""
        result = merge_config_and_args({'delay': 5.0}, {'delay': 2.0})

        self.assertEqual(result['delay'], 2.0)

    def test_unrelated_config_keys_pass_through(self):
        """Keys the CLI knows nothing about must survive the merge untouched."""
        result = merge_config_and_args({'s3_endpoint_url': 'https://minio.local'}, {'url': None})

        self.assertEqual(result['s3_endpoint_url'], 'https://minio.local')


if __name__ == '__main__':
    unittest.main()
