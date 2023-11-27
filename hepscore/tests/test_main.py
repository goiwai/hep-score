"""
Copyright 2019-2021 CERN.
See the COPYRIGHT file at the top-level directory
of this distribution. For licensing information, see the COPYING file at
the top-level directory of this distribution.
"""
from hepscore import main, hepscore
import io
import sys
import os
import logging
import unittest
from unittest.mock import patch
from parameterized import parameterized

logging.basicConfig(level=logging.DEBUG,
                    format='%(asctime)s - %(levelname)s - %(funcName)s() - %(message)s')
logger = logging.getLogger(__name__)

class Test_methods_main(unittest.TestCase):
    """Test arg_parse() in main()."""

    def test_version(self):
        with patch('sys.stdout', new=io.StringIO()) as fake_out:
            with self.assertRaises(SystemExit) as cm:
                main.parse_args(['-V'])
        self.assertEqual(cm.exception.code, 0)
        self.assertRegex(fake_out.getvalue(), r'\w+\s(\d+\.)+.*')
    
    def test_parse_args_return_type(self):
        # Test if parse_args returns a dictionary
        args = main.parse_args(['-v', '-m', 'docker', '/tmp'])
        self.assertIsInstance(args, dict)

    def test_missing_outdir(self):
        # Test if missing outdir fails with any param but -h
        with self.assertRaises(SystemExit) as cm:
            main.check_args(main.parse_args(["-v", "-c"]))
        self.assertEqual(cm.exception.code, 
                         main.exit_status_dict["Error missing outdir"])

    def test_do_not_fail_with_help_option(self):
        # Test missing outdir doesn't fail with -h
        with self.assertRaises(SystemExit) as cm:
            main.check_args(main.parse_args(['-h']))
        self.assertEqual(cm.exception.code, 0)

    def test_check_args_missing_outdir(self):
        # Test scenario when OUTDIR is missing
        with self.assertRaises(SystemExit) as cm:
            main.check_args({'OUTDIR': None, 'print': False, 'list': False})  # Missing OUTDIR
        self.assertEqual(cm.exception.code,
                         main.exit_status_dict["Error missing outdir"])
    
    def test_parse_args_conffile_and_builtinconf(self):
        # Test scenario when both conffile and builtinconf are specified
        with self.assertRaises(SystemExit) as cm:
            main.check_args(main.parse_args(['-f', 'config.yaml', '-b', 'sample', '/tmp']))
        self.assertEqual(cm.exception.code,
                         main.exit_status_dict["Error 2 config passed"])

    def test_check_args_conffile_and_builtinconf(self):
        # Test scenario when both conffile and builtinconf are specified
        with self.assertRaises(SystemExit) as cm:
            main.check_args({'OUTDIR': '/tmp', 'conffile': 'config.yaml', 'builtinconf': 'sample'})
        self.assertEqual(cm.exception.code,
                         main.exit_status_dict["Error 2 config passed"])
    

class Test_main(unittest.TestCase):
    @parameterized.expand([
        # Mock args and expected error codes
        # Fail if passing multiple config options
        (  
            ['-f', 'aconfig_file', '-b' , 'another_configfile', '/tmp'], 
            main.exit_status_dict['Error 2 config passed'] 
        ),
        # Fail if missing outdir
        (  
            [], 
            main.exit_status_dict['Error missing outdir'] 
        ),
        # Fail if format is wrong
        (  
            ['-f', '/tmp/notafile.txt', '/tmp'], 
            main.exit_status_dict['Error wrong configfile format'] 
        ),
        # Fail if hepscore or hepscore_benchmark is not the main key
        (  
            ['-f', '/'.join(os.path.split(__file__)[:-1]) + '/etc/hepscore_missing_key.yaml', '/tmp'], 
            main.exit_status_dict['Error malformed config file'] 
        ),
        # Fail replay if the input dir is wrong
        (
            ['-r', '/dummy'],
            main.exit_status_dict['Error missing resultdir']
        ),
        (
            ['-R', 'fake://fakeregistry', '/tmp'], 
            1),  # Override the configured registry
        ( 
            ['-p'], # Print configuration and exit
            main.exit_status_dict['Success'] 
        ),
        ( 
            ['-l'], # List built-in benchmark configurations and exit
            main.exit_status_dict['Success'] 
        ),
        ( 
            ['-h',], 
            main.exit_status_dict['Success'] 
        ),
        (['-V'],    # Display version
         main.exit_status_dict['Success']
         ),                    

    ])
    def test_exit_with_args(self, cli_args, expected_exit_code): 
        # add prog name at pos 0
        all_args = ['prog']
        all_args.extend(cli_args)
        print(all_args)

        with patch.object(hepscore.HEPscore, 'run') as mock_run, \
               patch.object(hepscore.HEPscore, 'gen_score') as mock_gen_score, \
                patch.object(hepscore.HEPscore, 'write_output') as mock_write_output:
        
            # Prepare the mock HEPscore object
            mock_run.return_value=0
            mock_gen_score.return_value=0
            mock_write_output.return_value=0

            with patch.object(sys,'argv', all_args):
                with self.assertRaises(SystemExit) as exit_code:
                    main.main()
                self.assertEqual(exit_code.exception.code, expected_exit_code)
    

    @parameterized.expand([
        # Mock args and expected error codes
        # Fail if passing multiple config options
            (['-i', 'dir','/tmp'],),  # container_uri
            (['-m', 'docker','/tmp'],),  # Docker container_exec
            (['-m', 'singularity','/tmp'],),  # Singularity
            (['-S', '/tmp'],),            # User namespace enabled
            (['-c', '/tmp'],),            # Clean residual container images
            (['-C', '/tmp'],),            # Clean residual files and directories
            (['-f', 
              '/'.join(os.path.split(__file__)[:-1]) + '/etc/hepscore_conf_ci.yaml', 
              '/tmp'],),  # Custom config yaml specified
            (['-R', 'oras://fakeregistry', '/tmp'],),  # Override the configured registry
            (['-b', 'hepscore-default', '/tmp'],),  # Use specified named built-in benchmark configuration
            (['-n', '4', '/tmp'],),       # Custom number of cores
            (['-o', 'output.json', '/tmp'],),  # Specify summary output file path/name
            (['-y', '/tmp'],),            # Create YAML summary output instead of JSON
            (['-v', '/tmp'],),            # Enable verbose mode
            (['-r', '/tmp'],),            # Replay output using existing results directory OUTDIR
            (['-r', '/'.join(os.path.split(__file__)[:-1]) + '/data/HEPscore_ci_allWLs'],)
    ])
    def test_main_with_args(self, cli_args): 
        # add prog name at pos 0
        all_args = ['prog']
        all_args.extend(cli_args)
        print(all_args)

        with patch.object(hepscore.HEPscore, 'run') as mock_run, \
               patch.object(hepscore.HEPscore, 'gen_score') as mock_gen_score, \
                patch.object(hepscore.HEPscore, 'write_output') as mock_write_output:
        
            # Prepare the mock HEPscore object
            mock_run.return_value=0
            mock_gen_score.return_value=0
            mock_write_output.return_value=0

            with patch.object(sys,'argv', all_args), \
                    patch('sys.stdout', new=io.StringIO()) as fake_out, \
                        patch('os.makedirs') as fake_makedirs:
                            fake_makedirs.return_value="HEPscore_01Gen2023_000000"
                            try:
                                main.main()
                            except SystemExit as exit_code:
                                self.fail("main.main() raised SystemExit unexpectedly with code {}".format(exit_code.code))
                            mock_run.assert_called_once()
                            mock_gen_score.assert_called_once()
                            mock_write_output.assert_called_once()


if __name__ == '__main__':
    unittest.main()

