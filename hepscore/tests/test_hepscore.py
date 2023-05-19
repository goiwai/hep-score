"""
Copyright 2019-2021 CERN.
See the COPYRIGHT file at the top-level directory
of this distribution. For licensing information, see the COPYING file at
the top-level directory of this distribution.
"""
from hepscore.hepscore import HEPscore
import json
import logging
import unittest
from unittest.mock import MagicMock, patch, mock_open
import yaml

logging.basicConfig(level=logging.DEBUG,
                    format='%(asctime)s - %(levelname)s - %(funcName)s() - %(message)s')
logger = logging.getLogger(__name__)

class test_arithmetic_methods(unittest.TestCase):
    """Utility methods."""

    def test_ordered_dict(self):
        """Reduntant test of upstream builtins.dict."""
        test_dict = {'b':2, 'c':3, 'a':1}
        self.assertEqual(str(test_dict), "{'b': 2, 'c': 3, 'a': 1}")
        test_dict['d'] = 4
        self.assertEqual(str(test_dict), "{'b': 2, 'c': 3, 'a': 1, 'd': 4}")
        self.assertNotEqual(sorted(test_dict), test_dict)

    def test_ordered_yaml_json(self):
        """Reduntant test of upstream PyYaml and builtins.json."""
        test_yaml = yaml.safe_load("""
        - B: 2
        - C: 3
        - A: 1
        """)
        self.assertEqual(test_yaml, [{'B': 2}, {'C': 3}, {'A': 1}])
        self.assertNotEqual(test_yaml, [{'A': 1}, {'B': 2}, {'C': 3}])
        self.assertEqual(yaml.safe_dump(test_yaml), "- B: 2\n- C: 3\n- A: 1\n")
        self.assertEqual(yaml.safe_dump(test_yaml, sort_keys=False), "- B: 2\n- C: 3\n- A: 1\n")
        self.assertNotEqual(yaml.safe_dump(test_yaml), "- A: 1\n- B: 2\n- C: 3\n")
        self.assertNotEqual(yaml.safe_dump(test_yaml, sort_keys=False), "- A: 1\n- B: 2\n- C: 3\n")

        self.assertEqual(json.dumps(test_yaml), '[{"B": 2}, {"C": 3}, {"A": 1}]')
        self.assertNotEqual(json.dumps(test_yaml), '[{"A": 1}, {"B": 2}, {"C": 3}]')
    # def test_median_tuple(self):
    
    # def test_weighted_geometric_mean(self):

class test_HEPscore(unittest.TestCase):
    """HEPscore method tests."""

    @patch('builtins.open', new_callable=mock_open)
    def test_write_output(self, mock_open):
        """Output as JSON or YAML."""
        assert mock_open
        fixture = MagicMock()
        fixture.confobj = {'settings': {'name': "test"}}
        fixture.resultsdir = "/tmp"
        fixture.results = [1,2]
        assert fixture.resultsdir == "/tmp"
        assert fixture.confobj == {'settings': {'name': "test"}}

        with self.assertRaises(ValueError):
            HEPscore.write_output(fixture, 'yml', 'garbage.yaml')

        HEPscore.write_output(fixture, 'yaml', 'out.yaml')
        mock_open.assert_called_once_with('out.yaml', mode='w')
        handle = mock_open()
        handle.write.assert_called_once_with('hepscore:\n  settings:\n    name: test\n')
        mock_open.reset_mock()

        HEPscore.write_output(fixture, 'yaml')
        mock_open.assert_called_once_with('/tmp/test.yaml', mode='w')
        handle = mock_open()
        handle.write.assert_called_once_with('hepscore:\n  settings:\n    name: test\n')
        mock_open.reset_mock()

        HEPscore.write_output(fixture, 'json', 'out.json')
        mock_open.assert_called_once_with('out.json', mode='w')
        handle.write.assert_called_once_with('{"settings": {"name": "test"}}')
        mock_open.reset_mock()

        HEPscore.write_output(fixture, 'json')
        mock_open.assert_called_once_with('/tmp/test.json', mode='w')
        handle.write.assert_called_once_with('{"settings": {"name": "test"}}')

        fixture.results = []
        with self.assertRaises(SystemExit) as context:
            HEPscore.write_output(fixture, 'yaml', 'out.yaml')
        self.assertEqual(context.exception.code, 2)

        fixture.results = [-1]
        with self.assertRaises(SystemExit) as context:
            HEPscore.write_output(fixture, 'yaml', 'out.yaml')
        self.assertEqual(context.exception.code, 2)

        fixture.results = [1]
        fixture.confobj['error'] = yaml
        with self.assertRaises(SystemExit) as context:
            HEPscore.write_output(fixture, 'yaml', 'out.yaml')
        self.assertEqual(context.exception.code, 2)

        with self.assertRaises(SystemExit) as context:
            HEPscore.write_output(fixture, 'json', 'out.json')
        self.assertEqual(context.exception.code, 2)

if __name__ == '__main__':
    unittest.main()
