# Copyright 2019-2021 CERN. See the COPYRIGHT file at the top-level directory
# of this distribution. For licensing information, see the COPYING file at
# the top-level directory of this distribution.

from dictdiffer import diff
from hepscore.hepscore import HEPscore
import json
import logging
import os
import yaml
from parameterized import parameterized
import shutil
import sys
import unittest
from unittest.mock import patch, mock_open

class Test_Constructor(unittest.TestCase):

    def test_fail_no_conf(self):
        with self.assertRaises(TypeError):
            HEPscore(resultsdir="/tmp")

    def test_fail_read_conf(self):
        with self.assertRaises(SystemExit):
            HEPscore(dict(), "/tmp")

    @patch.object(HEPscore, 'validate_conf')
    def test_succeed_read_set_defaults(self, mock_validate):
        standard = {'hepscore':
                    {'settings': {'name': 'test', 'registry': ['oras://abcd'],
                                  'reference_machine': 'unknown',
                                  'method': 'geometric_mean',
                                  'repetitions': 1}}}
        test_config = standard.copy()

        hs = HEPscore(test_config, "/tmp")

        self.assertEqual(hs.cec, "singularity")
        self.assertEqual(hs.resultsdir, "/tmp")
        self.assertEqual(hs.confobj, standard['hepscore'])

    @patch.object(HEPscore, 'validate_conf')
    def test_succeed_override_defaults(self, mock_validate):
        standard = {'hepscore':
                    {'settings': {'name': 'test', 'registry': ['docker://abcd'],
                                  'reference_machine': 'unknown',
                                  'method': 'geometric_mean',
                                  'repetitions': 1,
                                  'container_exec': 'docker'}}}
        test_config = standard.copy()

        hs = HEPscore(test_config, "/tmp1")

        self.assertEqual(hs.cec, "docker")
        self.assertEqual(hs.resultsdir, "/tmp1")
        self.assertEqual(hs.confobj, standard['hepscore'])

class TestRun(unittest.TestCase):

    def setUp(self):
        head, _ = os.path.split(__file__)
        self.path = os.path.normpath(
            os.path.join(head, 'etc/hepscore_conf_ci_helloworld.yaml'))
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

    @parameterized.expand([
    ('docker', 'docker', 0),  # 0 is UserWarning
    ('docker', 'oras',  1),   # 1 is SystemExit
    ('docker', 'dir', 1),
    ('singularity', 'docker',  0),
    ('singularity', 'oras',  0),
    ('singularity', 'dir',  0),
     ])
    def test_cec_curi_combinations(self, container_exec, container_uri , testidx):

        with open(self.path, 'r') as yam:
            test_config = yaml.full_load(yam)

        test_config['hepscore']['options'] = {'container_uri': container_uri}

        test_config['hepscore']['settings'].update(
            {'container_exec': container_exec}
        )

        if testidx == 0:
            self.assertIsInstance(HEPscore(test_config, "/tmp1"), HEPscore)
        elif testidx == 1:
            with self.assertRaises(SystemExit):
                HEPscore(test_config, "/tmp1")
        
    @parameterized.expand([
    ('docker', 'docker', "docker://abcd", 0),  # 0 is UserWarning
    ('docker', 'oras', "docker://abcd", 1),   # 1 is SystemExit
    ('docker', 'dir', "docker://abcd", 1),
    ('singularity', 'docker', "docker://abcd", 0),
    ('singularity', 'oras', "docker://abcd", 1),
    ('singularity', 'dir', "docker://abcd", 1),
    ('singularity', 'oras', "oras://abcd", 0),
    ('singularity', 'dir', "dir://abcd", 0),
     ])
    def test_cec_curi_combinations_string_registry(self, container_exec, container_uri , registry, testidx):

        with open(self.path, 'r') as yam:
            test_config = yaml.full_load(yam)

        test_config['hepscore']['options'] = {'container_uri': container_uri}

        test_config['hepscore']['settings'].update(
            {'registry' : registry ,
             'container_exec': container_exec}
        )

        if testidx == 0:
            self.assertIsInstance(HEPscore(test_config, "/tmp1"), HEPscore)
        elif testidx == 1:
            with self.assertRaises(SystemExit):
                HEPscore(test_config, "/tmp1")

    @parameterized.expand([
    ('docker', "docker://abcd", 0),
    ('docker', "oras://abcd", 1),
    ('singularity', "docker://abcd", 0),
    ('singularity',  "oras://abcd", 0),
    ('singularity',  "dir://abcd", 0),
     ])
    def test_cec_curi_combinations_string_registry_default(self, container_exec , registry, testidx):

        with open(self.path, 'r') as yam:
            test_config = yaml.full_load(yam)

        test_config['hepscore']['settings'].update(
            {'registry' : registry ,
            'container_exec': container_exec}
        )
        del test_config['hepscore']['options']['container_uri']

        if testidx == 0:
            self.assertIsInstance(HEPscore(test_config, "/tmp1"), HEPscore)
        elif testidx == 1:
            with self.assertRaises(SystemExit):
                HEPscore(test_config, "/tmp1")


class testOutput(unittest.TestCase):

    def test_parse_results(self):
        benchmarks = ["atlas-gen-bmk", "belle2-gen-sim-reco-bmk", "cms-digi-bmk", "cms-gen-sim-bmk",
                      "cms-reco-bmk", "lhcb-gen-sim-bmk"]

        head, _ = os.path.split(__file__)

        resDir = os.path.join(head, "data/HEPscore_ci_allWLs")

        conf = os.path.normpath(os.path.join(head, "etc/hepscore_conf.yaml"))

        with open(conf, 'r') as yam:
            test_config = yaml.full_load(yam)

        test_config['hepscore']['options'] = {}
        test_config['hepscore']['options']['level'] = 'DEBUG'
        test_config['hepscore']['options']['clean'] = True
        test_config['hepscore']['options']['clean_files'] = False

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
        actual_res = json.load(open(resDir + "/HEPscore2X.json"))

        result = list(diff(expected_res, actual_res, ignore=set(ignored_keys)))

        for entry in result:
            if len(entry[2]) == 1:
                print('\n\t %s :\n\t\t %s\t%s' % entry)
            else:
                print('\n\t %s :\n\t\t %s\n\t\t\t%s\n\t\t\t%s' %
                      (entry[0], entry[1], entry[2][0], entry[2][1]))

        self.assertEqual(len(result), 0)

        os.remove(resDir + "/HEPscore2X.json")
        os.remove(resDir + "/HEPscore2X.log")

    def test_parse_corrupt_results(self):
        head, _ = os.path.split(__file__)

        resDir = os.path.join(head, "data/HEPscore_ci_empty_score")

        conf = os.path.normpath(
            os.path.join(head, "etc/hepscore_conf.yaml"))

        with open(conf, 'r') as yam:
            test_config = yaml.full_load(yam)

        test_config['hepscore']['options'] = {}
        test_config['hepscore']['options']['level'] = 'DEBUG'
        test_config['hepscore']['options']['clean'] = True

        outtype = "json"
        outfile = ""

        hs = HEPscore(test_config, resDir)

        if hs.run(True) >= 0:
            hs.gen_score()
        with self.assertRaises(SystemExit) as ec:
            hs.write_output(outtype, outfile)
        self.assertEqual(ec.exception.code, 2)

        actual_res = json.load(open(resDir + "/HEPscore2X.json"))

        self.assertEqual(actual_res['score'], -1)
        self.assertEqual(actual_res['status'], "failed")

        os.remove(resDir + "/HEPscore2X.json")
        os.remove(resDir + "/HEPscore2X.log")


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
