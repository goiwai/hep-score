#!/usr/bin/env python3
###############################################################################
# Copyright 2019-2020 CERN. See the COPYRIGHT file at the top-level directory
# of this distribution. For licensing information, see the COPYING file at
# the top-level directory of this distribution.
###############################################################################
#
# hepscore.py - HEPscore benchmark execution
#

import glob
import hashlib
import json
import logging
import math
import multiprocessing
import operator
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import time
import yaml
from hepscore import __version__

logger = logging.getLogger(__name__)


def median_tuple(vals):

    sorted_vals = sorted(vals.items(), key=operator.itemgetter(1))

    med_ind = int(len(sorted_vals) / 2)
    if len(sorted_vals) % 2 == 1:
        return sorted_vals[med_ind][::-1]
    else:
        val1 = sorted_vals[med_ind - 1][1]
        val2 = sorted_vals[med_ind][1]
        return ((val1 + val2) / 2.0), (sorted_vals[med_ind - 1][0], sorted_vals[med_ind][0])


def weighted_geometric_mean(vals, weights=None):

    if weights is None:
        weights = []
        for i in vals:
            weights.append(1.0)

    if len(vals) != len(weights):
        return 0

    # Ensure we're dealing with floats
    vals = [float(x) for x in vals]
    weights = [float(x) for x in weights]

    total_weight = sum(weights)
    if total_weight == 0:
        return 0

    weighted_vals = [vals[i] ** weights[i] for i in range(len(vals))]

    total_val = 1
    for val in weighted_vals:
        total_val *= val

    weighted_gmean = total_val ** (1.0 / total_weight)

    return weighted_gmean


class HEPscore(object):

    NAME = "HEPscore"

    allowed_methods = {'geometric_mean': weighted_geometric_mean}
    scorekey = 'wl-scores'
    cec = "singularity"
    clean = False
    clean_files = False
    userns = False

    scache = ""
    registry = ""
    confobj = {}
    results = []
    weights = []
    score = -1

    def __init__(self, config, resultsdir):
        """Set & validate config, enable logging."""
        self.resultsdir = Path(resultsdir).resolve()
        self.confobj = config['hepscore_benchmark']
        self.settings = self.confobj['settings']

        if 'container_exec' in self.settings:
            if self.settings['container_exec'] in (
                    "singularity", "docker"):
                self.cec = self.settings['container_exec']
            else:
                logger.error("%s not understood. Stopping", self.settings['container_exec'])
                sys.exit(1)
        else:
            logger.warning("Container not specified on commandline or in config - assuming %s",
                           self.cec)

        if 'clean' in self.confobj.get('options', {}):
            self.clean = self.confobj['options']['clean']
            if self.cec == 'singularity':
                self.scache = self.resultsdir.joinpath('scache')
        if 'clean_files' in self.confobj.get('options', {}):
            self.clean_files = self.confobj['options']['clean_files']

        if 'userns' in self.confobj.get('options', {}):
            self.userns = self.confobj['options']['userns']

        self.confobj.pop('options', None)
        self.validate_conf()
        self.registry = self._gen_reg_path()

    def _gen_reg_path(self, reg_url=None):

        valid_uris = ['docker', 'shub', 'dir']
        if reg_url is None:
            try:
                reg_url = self.confobj['settings']['registry']
            except KeyError:
                logger.error("Registry undefined")
                sys.exit(1)

        found_valid = False
        for uri in valid_uris:
            if reg_url.find(uri + '://') == 0:
                found_valid = True
                reg_path = reg_url[len(uri) + 3:]
                break

        if not found_valid:
            logger.error("Invalid URI specification in registry path: %s", reg_url)
            sys.exit(1)

        # uri, reg_path possibly unbound
        if self.cec == 'docker' and uri != 'docker':
            logger.error("Only docker registry URI (docker://) supported for Docker runs.")
            sys.exit(1)
        return reg_path if (self.cec == 'docker' or uri == 'dir') else reg_url

    def _proc_results(self, benchmark):

        results = {}
        bench_conf = self.confobj['benchmarks'][benchmark]
        runs = int(self.confobj['settings']['repetitions'])

        benchmark_glob = benchmark.split('-')[:-1]
        benchmark_glob = '-'.join(benchmark_glob)

        summary_jsons = self.resultsdir.glob(benchmark_glob + '/**/*_summary.json')
        logger.debug("Looking for results in %s", sorted(summary_jsons))
        i = -1
        for summary_json in summary_jsons:
            i += 1
            logger.debug("Opening file %s", summary_json)

            try:
                with open(summary_json, mode='r') as jfile:
                    lines = jfile.read()
            except Exception:
                logger.error("Failure reading from %s", summary_json)
                continue

            try:
                jscore = ""
                jscore = json.loads(lines)
            except Exception:
                logger.error("Malformed JSON in %s", summary_json)
                continue

            json_required_keys = ['app', 'run_info', 'report']
            key_issue = False
            for k in json_required_keys:
                kstr = k
                if k not in jscore.keys():
                    key_issue = True
                elif k == 'report':
                    if (not isinstance(jscore[k], dict)) or self.scorekey not in jscore[k].keys():
                        key_issue = True
                        kstr = k + '[' + self.scorekey + ']'
                if key_issue:
                    logger.error("Required key '%s' not in JSON!", kstr)

            if key_issue:
                continue

            runstr = 'run' + str(i)
            if runstr not in bench_conf:
                bench_conf[runstr] = {}
            bench_conf[runstr]['report'] = jscore['report']

            if i == 0:
                bench_conf['app'] = jscore['app']
                bench_conf['run_info'] = jscore['run_info']

            sub_results = []
            for sub_bmk in bench_conf['ref_scores'].keys():
                if sub_bmk not in jscore['report'][self.scorekey]:
                    logger.error("Sub-score not reported for %s in %s!",
                                 sub_bmk, runstr)
                    key_issue = True
                    continue
                sub_score = float(jscore['report'][self.scorekey][sub_bmk])
                sub_score = sub_score / bench_conf['ref_scores'][sub_bmk]
                sub_score = round(sub_score, 4)
                sub_results.append(sub_score)

            if key_issue:
                continue

            score = weighted_geometric_mean(sub_results)

            results[i] = round(score, 4)
            logger.debug(results[i])

        if len(results) == 0:
            logger.warning("No results: fail")
            return -1

        if len(results) != runs:
            logger.error("Expected %d scores, got %d!", runs, len(results))
            return -1

        final_result, final_run = median_tuple(results)

    #   Insert wl-score from chosen run
        if 'wl-scores' not in self.confobj:
            self.confobj['wl-scores'] = {}
        self.confobj['wl-scores'][benchmark] = {}

        for sub_bmk in bench_conf['ref_scores'].keys():
            if len(results) % 2 != 0:
                runstr = 'run' + str(final_run)
                logger.debug("Median selected run %s", runstr)
                self.confobj['wl-scores'][benchmark][sub_bmk] = \
                    bench_conf[runstr]['report']['wl-scores'][sub_bmk]
            else:
                avg_names = ['run' + str(rv) for rv in final_run]
                sum_score = 0
                for runstr in avg_names:
                    sum_score += bench_conf[runstr]['report']['wl-scores'][sub_bmk]
                    self.confobj['wl-scores'][benchmark][sub_bmk] = sum_score / 2

            self.confobj['wl-scores'][benchmark][sub_bmk + '_ref'] = \
                bench_conf['ref_scores'][sub_bmk]

        bench_conf.pop('ref_scores', None)

        if len(results) > 1:
            logger.debug(" Median: %s", final_result)

        return final_result

    def _container_rm(self, image):
        if self.clean is False:
            return False

        try:
            if self.cec == 'docker':
                logger.info("Deleting Docker image %s", image)
                command = "docker rmi -f " + image
                logger.debug(command)
                command = command.split(' ')
                ret = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
                ret.wait()
            elif self.cec == 'singularity' and self.scache != "":
                # remove scache only if nested in rundir
                if self.resultsdir in self.scache.parents:
                    logger.info("Removing temporary singularity cache %s", self.scache)
                    shutil.rmtree(self.scache)
                else:
                    return False
        except Exception:
            logger.error("Failed to cleanup image!")
            return False

        return True

    def check_userns(self):
        proc_muns = "/proc/sys/user/max_user_namespaces"
        dockerenv = "/.dockerenv"

        try:
            cg = open(dockerenv, mode='r')
            cg.close()
            logger.debug("%s running inside of Docker. Not enabling user namespaces.", self.NAME)
            return False
        except Exception:
            logger.debug("%s not running inside Docker.", self.NAME)

        try:
            mf = open(proc_muns, mode='r')
            max_usrns = int(mf.read())
        except Exception:
            logger.debug("Cannot open/read from %s, assuming user namespace support disabled",
                         proc_muns)
            return False

        mf.close()
        return bool(max_usrns)

    # User namespace flag needed to support nested singularity
    def _get_usernamespace_flag(self):
        if self.cec == "singularity" and self.userns is True:
            if self.check_userns():
                logger.debug("System supports user namespaces, enabling in singularity call")
                return "-u "
        return ""

    def get_version(self):

        commands = {'docker': "docker --version",
                    'singularity': "singularity --version"}

        try:
            command = commands[self.cec].split(' ')
            cmdf = subprocess.Popen(command, stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT)
        except Exception:
            logger.error("Error fetching %s version", self.cec)

        try:
            # cmdf possibly unbound
            line = cmdf.stdout.readline()
            line = line.decode('utf-8')

            while line:
                version = line
                if version[-1] == "\n":
                    version = version[:-1]
                line = cmdf.stdout.readline()
            # version possibly unbound
            return version
        except Exception:
            return "error"

    def _run_benchmark(self, benchmark, mock):

        bench_conf = self.confobj['benchmarks'][benchmark]
        options_string = ""
        output_logs = ['']
        bmark_keys = ''
        bmark_registry = self.registry
        bmark_reg_url = self.confobj['settings']['registry']
        result = 0
        gpu_flag = ""

        runs = int(self.confobj['settings']['repetitions'])
        logfile_path = self.resultsdir.joinpath(self.confobj['settings']['name'] + ".log")

        if 'retries' in self.confobj['settings']:
            retries = int(self.confobj['settings']['retries'])
        else:
            retries = 0
        successful_runs = 0
        retry_count = 0

        tmp = "Executing " + str(runs) + " run"
        if runs > 1:
            tmp += 's'
        logger.info("%s of %s", tmp, benchmark)

        if 'args' in bench_conf.keys():
            bmark_keys = bench_conf['args'].keys()

        # Allow registry overrides in the benchmark configuration
        if 'registry' in bench_conf.keys():
            bmark_reg_url = bench_conf['registry']
            bmark_registry = self._gen_reg_path(bench_conf['registry'])
            logger.info("Overriding registry for this container: %s", bmark_reg_url)

        if self.clean_files is True:
            options_string = " --mop all"

        if 'gpu' in bench_conf and bench_conf['gpu'] is True:
            if self.cec == 'singularity':
                gpu_flag = "--nv "
            else:
                gpu_flag = "--gpus all "

        for option in bmark_keys:
            bad_args = ["mop", "resultsdir", "--mop", "--resultsdir",
                        "-m", "-w", "-W"]
            option_arg = str(bench_conf['args'][option])

            if re.match(r'^[a-zA-Z0-9\-_]*$', option) is None or \
                    option in bad_args or \
                    re.match(r'^[a-zA-Z0-9\-_]*$', option_arg) \
                    is None:
                logger.error("Ignoring invalid option in YAML configuration %s %s",
                             option, option_arg)
                continue
            if option_arg not in ['None', 'False']:
                if option[0] != '-':
                    options_string = options_string + ' ' + '--' + option
                else:
                    options_string = options_string + ' ' + option
                if option_arg != 'True':
                    options_string = options_string + ' ' + option_arg

        try:
            lfile = open(logfile_path, mode='a')
        except Exception:
            logger.error("failure to open %s", logfile_path)
            return -1

        benchmark_name = bmark_registry + '/' + benchmark + ':' + bench_conf['version']
        benchmark_complete = benchmark_name + options_string
        self.confobj['settings']['replay'] = mock

        if self.cec == 'singularity' and self.scache != "":
            logger.info("Creating singularity cache %s", self.scache)
            try:
                self.scache.mkdir()
                os.environ['SINGULARITY_CACHEDIR'] = self.scache
            except Exception:
                logger.error("Failed to create Singularity cache dir %s", self.scache)

        for i in range(runs + retries):
            if successful_runs == runs:
                break

            runDir = self.resultsdir.joinpath(benchmark[:-4], "run" + str(i))
            logsFile = runDir.joinpath(self.cec + "_logs")

            if self.confobj['settings']['replay'] is False:
                runDir.mkdir()
                if self.cec == 'docker':
                    runDir.chmod(0o1777)

            commands = {'docker': "docker run --rm --network=host -v " + str(runDir)
                                  + ":/results " + gpu_flag,
                        'singularity': "singularity run -C -B " + str(runDir) + ":/results -B /tmp "
                                       + self._get_usernamespace_flag() + gpu_flag}

            command_string = commands[self.cec] + benchmark_complete
            command = command_string.split(' ')

            runstr = 'run' + str(i)

            logger.info("Starting %s", runstr)
            logger.debug("Running  %s", command)

            bench_conf[runstr] = {}
            starttime = time.time()
            bench_conf[runstr]['start_at'] = time.ctime(starttime)
            if not mock:
                try:
                    cmdf = subprocess.Popen(command, stdout=subprocess.PIPE,
                                            stderr=subprocess.STDOUT)
                except Exception:
                    if self.cec == 'docker':
                        runDir.chmod(0o1777)

                    logger.error("failure to execute: %s", command_string)
                    bench_conf['run' + str(i)]['end_at'] = bench_conf['run' + str(i)]['start_at']
                    bench_conf['run' + str(i)]['duration'] = 0
                    retry_count += 1
                    if retries <= 0 or retry_count > retries:
                        result = -1
                        break
                    logger.error("Retrying...")
                    continue

                line = cmdf.stdout.readline()
                while line:
                    output_logs.insert(0, line)
                    lfile.write(line.decode('utf-8'))
                    lfile.flush()
                    line = cmdf.stdout.readline()
                    if line[-25:] == "no space left on device.\n":
                        logger.error("Docker: No space left on device.")

                cmdf.wait()

                if self.cec == 'docker':
                    os.chmod(runDir, stat.S_IRWXU | stat.S_IRGRP |
                             stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH)

                self._check_rc(cmdf.returncode)
                if cmdf.returncode > 0:
                    logger.error("%s output logs:", self.cec)
                    for line in list(reversed(output_logs))[-10:]:
                        logger.error(line)
                else:
                    successful_runs += 1

                try:
                    with open(logsFile, 'w') as f:
                        for line in reversed(output_logs):
                            f.write('%s' % line)
                except Exception:
                    logger.warning("Failed to write logs to file!")

            else:
                time.sleep(1)

            endtime = time.time()
            bench_conf[runstr]['end_at'] = time.ctime(endtime)
            bench_conf[runstr]['duration'] = math.floor(endtime) - math.floor(starttime)

            # cmdf possibly unbound
            if not mock and cmdf.returncode != 0:
                logger.error("running %s failed.  Exit status %s", benchmark, cmdf.returncode)

                retry_count += 1
                if retries <= 0 or retry_count > retries:
                    result = -1
                    break
                logger.warning("Retrying...")

        lfile.close()
        self._container_rm(benchmark_name)
        logger.info("")

        proc_result = self._proc_results(benchmark)
        return proc_result if result != -1 else result

    def _check_rc(self, rc):
        if rc == 137 and self.cec == 'docker':
            logger.error("%s returned code 137: OOM-kill or intervention", self.cec)
        elif rc != 0:
            logger.error("%s returned code %s", self.cec, rc)
        else:
            logger.debug("%s terminated without errors", self.cec)

    def gen_score(self):

        method = self.allowed_methods[self.confobj['settings']['method']]
        fres = method(self.results, self.weights)
        if 'scaling' in self.confobj['settings'].keys():
            fres = fres * self.confobj['settings']['scaling']

        fres = round(fres, 4)

        logger.info("Final result: %s", fres)

        if math.isnan(fres):
            logger.debug("Final result is not valid")
            self.confobj['score_per_core'] = -1
            self.confobj['score'] = -1
            self.confobj['status'] = 'failed'
        else:
            self.confobj['score'] = float(fres)
            self.confobj['status'] = 'success'
            try:
                spc = float(fres) / float(multiprocessing.cpu_count())
                self.confobj['score_per_core'] = round(spc, 3)
            except Exception:
                self.confobj['score_per_core'] = -1
                logger.warning('Could not determine core count')

    def write_output(self, outtype, outfile=None):

        if not outfile:
            outfile = self.resultsdir.joinpath(self.confobj['settings']['name'] + '.' + outtype)
        outfile = Path(outfile)

        # check outfile is same type as outtype
        if '.' + outtype != outfile.suffix:
            logging.error("%s output requested, but %s does not match!", outtype, outfile)

        outobj = {}
        if outtype == 'yaml':
            outobj['hepscore_benchmark'] = self.confobj
        elif outtype == 'json':
            outobj = self.confobj
        else:
            raise ValueError("outtype must be 'json' or 'yaml'")

        try:
            with open(outfile, mode='w') as output:
                if outtype == 'yaml':
                    output.write(yaml.safe_dump(outobj, sort_keys=False))
                else:
                    output.write(json.dumps(outobj))
        except Exception:
            logging.error("Failed to create summary output %s", outfile)
            sys.exit(2)

        if len(self.results) == 0 or self.results[-1] < 0:
            logger.error("Results = %s.", self.results)
            sys.exit(2)

    def validate_conf(self):

        hep_settings = ['settings', 'benchmarks']
        rsf = {'settings': ['method', 'repetitions', 'name', 'registry', 'reference_machine'],
               'benchmarks': []}

        for k in hep_settings:
            if k not in self.confobj:
                logger.error("Configuration: %s section must be defined", k)
                sys.exit(1)

            for f in rsf[k]:
                if f not in self.confobj[k]:
                    logger.error("Configuration: %s must be specified in %s", f, k)
                    sys.exit(1)

            if k == 'settings':
                for j in self.confobj[k]:
                    if j == 'registry':
                        reg_string = \
                            self.confobj[k][j]
                        if not reg_string[0].isalpha() or \
                                re.match(r'^[a-zA-Z0-9:/\-_\.~]*$', reg_string) is None:
                            logger.error("Configuration: illegal character in registry")
                            sys.exit(1)
                    if j == 'method':
                        val = self.confobj[k][j]
                        if val != 'geometric_mean':
                            logger.error("Configuration: only 'geometric_mean' method is "
                                         "currently supported")
                            sys.exit(1)
                    if j in ('repetitions', 'retries'):
                        val = self.confobj[k][j]
                        if (not isinstance(val, int)) or val < 0:
                            logger.error("Configuration: '%s' configuration parameter must "
                                         "be a positive integer", j)
                            sys.exit(1)
                    if j == 'scaling':
                        try:
                            float(self.confobj[k][j])
                        except ValueError:
                            logger.error("Configuration: 'scaling' configuration parameter "
                                         "must be a float")
                            sys.exit(1)

        bcount = 0
        for benchmark in list(self.confobj['benchmarks']):
            bmark_conf = self.confobj['benchmarks'][benchmark]
            bcount = bcount + 1

            if benchmark[0] == ".":
                logger.info("%s is commented out: Skipping this benchmark!", benchmark)
                self.confobj['benchmarks'].pop(benchmark, None)
                continue

            if re.match(r'^[a-zA-Z0-9\-_]*$', benchmark) is None:
                logger.error("Configuration: illegal character in benchmark name %s", benchmark)
                sys.exit(1)

            if benchmark.find('-') == -1:
                logger.error("Configuration: expect at least 1 '-' character in benchmark name %s",
                             benchmark)
                sys.exit(1)

            bmk_req_options = ['version']

            for k in bmk_req_options:
                if k not in bmark_conf.keys():
                    logger.error("Configuration: missing required benchmark option for %s - %s",
                                 benchmark, k)
                    sys.exit(1)

            if 'weight' in bmark_conf.keys():
                try:
                    float(bmark_conf['weight'])
                except ValueError:
                    logger.error("Configuration: invalid 'weight' specified: %s Must be a float",
                                 bmark_conf['weight'])

            if 'ref_scores' in bmark_conf.keys():
                for score in bmark_conf['ref_scores']:
                    try:
                        float(bmark_conf['ref_scores'][score])
                    except ValueError:
                        logger.error("Configuration: ref_score %s is not a float for %s",
                                     score, benchmark)
                        sys.exit(1)
            else:
                logger.error("Configuration: ref_scores missing for %s", benchmark)
                sys.exit(1)

            if 'registry' in bmark_conf.keys():
                # reg_string possibly unbound
                if not reg_string[0].isalpha() or \
                        re.match(r'^[a-zA-Z0-9:/\-_\.~]*$', reg_string) is None:
                    logger.error("Configuration: illegal character in registry")
                    sys.exit(1)

        if bcount == 0:
            logger.error("Configuration: no benchmarks specified")
            sys.exit(1)

        logger.debug("The parsed config is: %s", yaml.safe_dump(self.confobj, sort_keys=False))

        return self.confobj

    def run(self, mock=False):

        # check rundir is empty
        if any(self.resultsdir.iterdir()) and not mock:
            logger.error("Results directory is not empty!")
            sys.exit(2)

        # Creating a hash representation of the configuration object
        # to be included in the final report
        m = hashlib.sha256()
        hashable_conf = {k: v for k, v in self.confobj.items() if k not in 'options'}
        m.update(json.dumps(hashable_conf, sort_keys=True).encode('utf-8'))
        self.confobj['app_info'] = {}
        self.confobj['app_info']['config_hash'] = m.hexdigest()

        sysname = ' '.join(os.uname())
        curtime = time.asctime()

        ver = self.get_version()
        exec_ver = self.cec + "_version"

        self.confobj['environment'] = {'system': sysname, 'date': curtime, exec_ver: ver}

        logger.info("%s Benchmark", self.confobj['settings']['name'])
        logger.info("Config Hash:         %s", self.confobj['app_info']['config_hash'])
        logger.info("System:              %s", sysname)
        logger.info("Container Execution: %s", self.cec)
        logger.info("Registry:            %s", self.confobj['settings']['registry'])
        logger.info("Output:              %s", self.resultsdir)
        logger.info("Date:                %s\n", curtime)

        self.confobj['wl-scores'] = {}
        self.confobj['app_info']['hepscore_ver'] = __version__

        if mock is True:
            logging.info("NOTE: Replaying prior results")

        res = 0
        have_failure = False
        for benchmark in self.confobj['benchmarks']:
            res = self._run_benchmark(benchmark, mock)
            if res < 0:
                have_failure = True
                # set error to first benchmark encountered
                if 'error' not in self.confobj.keys():
                    self.confobj['error'] = benchmark
                if 'continue_fail' not in self.confobj['settings'].keys() or \
                        self.confobj['settings']['continue_fail'] is False:
                    break
            self.results.append(res)
            bench_conf = self.confobj['benchmarks'][benchmark]
            if 'weight' in bench_conf:
                self.weights.append(bench_conf['weight'])
            else:
                self.weights.append(1.0)
                bench_conf['weight'] = 1.0

        if have_failure:
            logger.error("BENCHMARK FAILURE")
            self.confobj['score'] = -1
            self.confobj['status'] = 'failed'
            return -1

        return res
# End of HEPscore class
