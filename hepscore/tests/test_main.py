"""
Copyright 2019-2021 CERN.
See the COPYRIGHT file at the top-level directory
of this distribution. For licensing information, see the COPYING file at
the top-level directory of this distribution.
"""
from hepscore import main
import io
import logging
import unittest
from unittest.mock import patch

logging.basicConfig(level=logging.DEBUG,
                    format='%(asctime)s - %(levelname)s - %(funcName)s() - %(message)s')
logger = logging.getLogger(__name__)

class Test_parse_args(unittest.TestCase):
    """Test arg_parse() in main()."""
    def test_c_option_fails(self):
        with self.assertRaises(SystemExit) as cm:
            main.parse_args(["-v", "-c"])
        self.assertEqual(cm.exception.code, 2)

    def test_h_option(self):
        with self.assertRaises(SystemExit) as cm:
            main.parse_args(['-h'])
        self.assertEqual(cm.exception.code, 0)

    def test_version(self):
        with patch('sys.stdout', new=io.StringIO()) as fake_out:
            with self.assertRaises(SystemExit) as cm:
                main.parse_args(['-V'])
        self.assertEqual(cm.exception.code, 0)
        self.assertRegex(fake_out.getvalue(), r'\w+\s(\d+\.)+.*')

    def test_require_outdir(self):
        with self.assertRaises(SystemExit) as cm:
            main.main()
        self.assertEqual(cm.exception.code, 2)

    def test_return_type(self):
        res = main.parse_args(["/tmp"])
        self.assertIsInstance(res, dict)

class Test_main(unittest.TestCase):
    """Test main() function."""
    def setUp(self):
         #self.mock_hepscore = patch('HEPscore', autospec=True)
        self.mock_parse = patch.object(main, 'parse_args')
        self.mock_conf_path = "etc/hepscore_empty_conf.yaml"
        self.mock_bad_path = "/tmp/notafile.txt"
        self.mock_args = {'OUTDIR': '/tmp',
                         'container_exec': False,
                         'userns': False,
                         'clean': False,
                         'cleanall': False,
                         'conffile': self.mock_bad_path,
                         'builtinconf': '',
                         'replay': False,
                         'resultsdir': False,
                         'outfile': False,
                         'yaml': False,
                         'print': False,
                         'list': False,
                         'verbose': False}
        self.mock_parse.return_value = self.mock_args

    @patch.object(main, 'parse_args')
    def test_read_config(self, mock_parse):
        mock_parse.return_value=self.mock_args
        # with patch('builtins.open', mock_open(read_data="2")) as mock_file
        with self.assertRaises(SystemExit) as exit_code:
            main.main()
        mock_parse.assert_called_once()
        self.assertEqual(exit_code.exception.code, 1)


if __name__ == '__main__':
    unittest.main()
