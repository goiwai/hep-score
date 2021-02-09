# Copyright 2019-2020 CERN. See the COPYRIGHT file at the top-level directory
# of this distribution. For licensing information, see the COPYING file at
# the top-level directory of this distribution.

from dictdiffer import diff
from hepscore.hepscore import HEPscore
import json
import logging
import os
from pathlib import Path
import yaml
# from parameterized import parameterized
import shutil
import sys
import unittest
from unittest.mock import patch, mock_open


class Test_Constructor(unittest.TestCase):

    def test_fail_no_conf(self):
        with self.assertRaises(TypeError):
            HEPscore(resultsdir="/tmp")

    def test_fail_read_conf(self):
        with self.assertRaises(KeyError):
            HEPscore(dict(), "/tmp")

    @patch.object(HEPscore, 'validate_conf')
    def test_succeed_read_set_defaults(self, mock_validate):
        standard = {'hepscore_benchmark':
                    {'settings': {'name': 'test', 'registry': 'docker://',
                                  'reference_machine': 'unknown',
                                  'method': 'geometric_mean',
                                  'repetitions': 1}}}
        test_config = standard.copy()

        hs = HEPscore(test_config, "/tmp")

        self.assertEqual(hs.cec, "singularity")
        self.assertEqual(hs.resultsdir, Path("/tmp"))
        self.assertEqual(hs.confobj, standard['hepscore_benchmark'])

    @patch.object(HEPscore, 'validate_conf')
    def test_succeed_override_defaults(self, mock_validate):
        standard = {'hepscore_benchmark':
                    {'settings': {'name': 'test', 'registry': 'docker://',
                                  'reference_machine': 'unknown',
                                  'method': 'geometric_mean',
                                  'repetitions': 1,
                                  'container_exec': 'singularity'}}}
        test_config = standard.copy()

        hs = HEPscore(test_config, "/tmp1")

        self.assertEqual(hs.cec, "singularity")
        self.assertEqual(hs.resultsdir, Path("/tmp1"))
        self.assertEqual(hs.confobj, standard['hepscore_benchmark'])


class TestRun(unittest.TestCase):

    def setUp(self):
        head, _ = os.path.split(__file__)
        self.path = os.path.normpath(
            os.path.join(head, 'etc/hepscore_conf_bmsreco_only.yaml'))
        self.emptyPath = os.path.normpath(
            os.path.join(head, 'etc/hepscore_empty_conf.yaml'))
        self.resPath = os.path.normpath(head)

    def test_run_empty_cfg(self):

        if not os.path.exists('/tmp/test_run_empty_cfg'):
            os.mkdir('/tmp/test_run_empty_cfg')

        with open(self.emptyPath, 'r') as yam:
            test_config = yaml.full_load(yam)

        # what is this testing?
        hs = HEPscore(test_config, "/tmp/test_run_empty_cfg")
        if hs.run(False) >= 0:
            hs.gen_score()
        with self.assertRaises(SystemExit) as cm:
            hs.write_output("json", "")
            self.assertEqual(cm.exception.code, 2)
        shutil.rmtree("/tmp/test_run_empty_cfg")


class testOutput(unittest.TestCase):

    def test_parse_results(self):
        benchmarks = ["atlas-gen-bmk", "cms-digi-bmk", "cms-gen-sim-bmk",
                      "cms-reco-bmk", "lhcb-gen-sim-bmk"]

        head, _ = os.path.split(__file__)

        resDir = os.path.join(head, "data/HEPscore_ci_allWLs")

        conf = os.path.normpath(os.path.join(head, "etc/hepscore_conf.yaml"))

        with open(conf, 'r') as yam:
            test_config = yaml.full_load(yam)

        test_config['hepscore_benchmark']['options'] = {}
        test_config['hepscore_benchmark']['options']['level'] = 'DEBUG'
        test_config['hepscore_benchmark']['options']['clean'] = True
        test_config['hepscore_benchmark']['options']['clean_files'] = False

        outtype = "json"
        outfile = ""

        hs = HEPscore(test_config, resDir)

        ignored_keys = ['app_info.hash', 'environment', 'settings.replay',
                        'app_info.hepscore_ver', 'score_per_core', 'score']

        for benchmark in benchmarks:
            ignored_keys.append("benchmarks." + benchmark + ".run0")
            ignored_keys.append("benchmarks." + benchmark + ".run1")
            ignored_keys.append("benchmarks." + benchmark + ".run2")

        hs.run(True)
        hs.gen_score()
        hs.write_output(outtype, outfile)

        expected_res = json.load(
            open(resDir + "/hepscore_result_expected_output.json"))
        actual_res = json.load(open(resDir + "/HEPscore20.json"))

        result = list(diff(expected_res, actual_res, ignore=set(ignored_keys)))

        for entry in result:
            if len(entry[2]) == 1:
                print('\n\t %s :\n\t\t %s\t%s' % entry)
            else:
                print('\n\t %s :\n\t\t %s\n\t\t\t%s\n\t\t\t%s' %
                      (entry[0], entry[1], entry[2][0], entry[2][1]))

        self.assertEqual(len(result), 0)

        os.remove(resDir + "/HEPscore20.json")
        os.remove(resDir + "/HEPscore20.log")

    def test_parse_corrupt_results(self):
        head, _ = os.path.split(__file__)

        resDir = os.path.join(head, "data/HEPscore_ci_empty_score")

        conf = os.path.normpath(
            os.path.join(head, "etc/hepscore_conf.yaml"))

        with open(conf, 'r') as yam:
            test_config = yaml.full_load(yam)

        test_config['hepscore_benchmark']['options'] = {}
        test_config['hepscore_benchmark']['options']['level'] = 'DEBUG'
        test_config['hepscore_benchmark']['options']['clean'] = True

        outtype = "json"
        outfile = ""

        hs = HEPscore(test_config, resDir)

        if hs.run(True) >= 0:
            hs.gen_score()
        with self.assertRaises(SystemExit) as ec:
            hs.write_output(outtype, outfile)
        self.assertEqual(ec.exception.code, 2)

        actual_res = json.load(open(resDir + "/HEPscore20.json"))

        self.assertEqual(actual_res['score'], -1)
        self.assertEqual(actual_res['status'], "failed")

        os.remove(resDir + "/HEPscore20.json")
        os.remove(resDir + "/HEPscore20.log")


if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG,
                        format='%(asctime)s - %(levelname)s - '
                        '%(funcName)s() - %(message)s',
                        stream=sys.stdout)
    unittest.main()


# Config:
# - Get conf from yaml, validate V
#
# WL Runner:
# - Run in sequence the list of WL's in config, store results
#
# Report:
# - Access WL Jsons
# - Validate WL results
# - Compute geom mean
# - Summarise WL Exit status
# - Build HEP-score json report
