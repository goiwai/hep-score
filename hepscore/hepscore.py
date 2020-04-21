#!/usr/bin/python
###############################################################################
#
# hepscore.py - HEPscore benchmark execution
#

import getopt
import glob
import hashlib
import json
import math
import operator
import os
import subprocess
import sys
import time
import yaml


NAME = "HEPscore"
VER = "0.64"
DEBUG = False

CONF = """
hepscore_benchmark:
  benchmarks:
    atlas-gen-bmk:
      ref_scores:
        gen: 207.6
      scorekey: wl-scores
      threads: 1
      version: v1.1
    atlas-sim-bmk:
      ref_scores:
        sim: 0.028
      scorekey: wl-scores
      threads: 4
      version: v1.0
    atlas-digi-reco-bmk:
      ref_scores:
        digi-reco: 1.211
      scorekey: wl-scores
      threads: 4
      events: 30
      version: v1.0
    cms-gen-sim-bmk:
      ref_scores:
        gen-sim: 0.362
      scorekey: wl-scores
      version: v1.0
    cms-digi-bmk:
      ref_scores:
        digi: 1.94
      scorekey: wl-scores
      version: v1.0
    cms-reco-bmk:
      ref_scores:
        reco: 1.117
      scorekey: wl-scores
      version: v1.0
    lhcb-gen-sim-bmk:
      ref_scores:
        gen-sim: 41.32
      scorekey: wl-scores
      version: v0.15
  method: geometric_mean
  name: HEPscore19
  reference_machine: "bmk16-cc7-7xc9mygbzq"
  registry: gitlab-registry.cern.ch/hep-benchmarks/hep-workloads
  repetitions: 3
  scaling: 1
  container_exec: docker
  version: 0.3
"""


def help():

    global NAME

    namel = NAME.lower() + ".py"

    print(NAME + " Benchmark Execution - Version " + VER)
    print(namel + " [-s|-d] [-v] [-V] [-y] [-o OUTFILE] [-f CONF] OUTDIR")
    print(namel + " -h")
    print(namel + " -p [-f CONF]")
    print("Option overview:")
    print("-h           Print help information and exit")
    print("-v           Display verbose output, including all component "
          "benchmark scores")
    print("-d           Run benchmark containers in Docker")
    print("-s           Run benchmark containers in Singularity")
    print("-f           Use specified YAML configuration file (instead of "
          "built-in)")
    print("-o           Specify an alternate summary output file location")
    print("-y           Specify output file should be YAML instead of JSON")
    print("-p           Print configuration and exit")
    print("-V           Enable debugging output: implies -v")
    print("Examples:")
    print("Run the benchmark using Docker, dispaying all component scores:")
    print(namel + " -dv /tmp/hs19")
    print("Run with Singularity, using a non-standard benchmark "
          "configuration:")
    print(namel + " -sf /tmp/hscore/hscore_custom.yaml /tmp/hscore\n")
    print("Additional information: https://gitlab.cern.ch/hep-benchmarks/hep-"
          "score")
    print("Questions/comments: benchmark-suite-wg-devel@cern.ch")


def debug_print(dstring, newline):
    global DEBUG

    if DEBUG:
        if newline:
            print("")
        print("DEBUG: " + dstring)


def proc_results(benchmark, rpath, verbose, conf):

    results = {}
    fail = False
    overall_refscore = 1.0
    bench_conf = conf['benchmarks'][benchmark]
    key = bench_conf['scorekey']
    runs = int(conf['repetitions'])

    if 'refscore' in bench_conf.keys():
        if bench_conf['refscore'] is None:
            overall_refscore = 1.0
        else:
            overall_refscore = float(bench_conf['refscore'])

    if benchmark == "kv-bmk":
        benchmark_glob = "test_"
    else:
        benchmark_glob = benchmark.split('-')[:-1]
        benchmark_glob = '-'.join(benchmark_glob)

    gpaths = glob.glob(rpath + "/" + benchmark_glob + "*/" +
                       benchmark_glob + "_summary.json")

    debug_print("Looking for results in " + str(gpaths), False)
    i = 0
    for gpath in gpaths:
        debug_print("Opening file " + gpath, False)
        jscore = ""

        jfile = open(gpath, mode='r')
        line = jfile.readline()
        jfile.close()

        try:
            jscore = json.loads(line)
            runstr = 'run' + str(i)
            if runstr not in bench_conf:
                bench_conf[runstr] = {}
            bench_conf[runstr]['report'] = jscore

            if 'ref_scores' not in bench_conf.keys():
                if 'subkey' in bench_conf.keys():
                    subkey = bench_conf['subkey']
                    score = float(jscore[key][subkey]['score'])
                else:
                    score = float(jscore[key]['score'])

                score = score / overall_refscore
            else:
                sub_results = []
                for sub_bmk in bench_conf['ref_scores'].keys():
                    sub_score = float(jscore[key][sub_bmk])
                    sub_score = sub_score / bench_conf['ref_scores'][sub_bmk]
                    sub_results.append(sub_score)
                score = geometric_mean(sub_results)
        except Exception:
            if not fail:
                print("\nError: score not reported for one or more runs.")
                if len(jscore) > 0:
                    print("The retrieved json report contains\n%s" % jscore)

                fail = True

        if not fail:
            results[i] = score

            if verbose:
                print(" " + str(score))

        i = i + 1

    if len(results) == 0:
        print("\nNo results: fail")
        return(-1)

    if len(results) != runs:
        fail = True
        print("\nError: missing json score file for one or more runs")

    if fail:
        if 'allow_fail' not in conf.keys() or conf['allow_fail'] is False:
            return(-1)

    final_result, final_run = median_tuple(results)

#   Insert wl-score from chosen run
    if 'wl-scores' not in conf:
        conf['wl-scores'] = {}
    conf['wl-scores'][benchmark] = {}

    if 'ref_scores' in bench_conf.keys():
        for sub_bmk in bench_conf['ref_scores'].keys():
            if len(results) % 2 != 0:
                runstr = 'run' + str(final_run)
                debug_print("Median selected run " + runstr, True)
                conf['wl-scores'][benchmark][sub_bmk] = \
                    bench_conf[runstr]['report']['wl-scores'][sub_bmk]
            else:
                avg_names = ['run' + str(rv) for rv in final_run]
                sum = 0
                for runstr in avg_names:
                    sum = sum + \
                        bench_conf[runstr]['report']['wl-scores'][sub_bmk]
                conf['wl-scores'][benchmark][sub_bmk] = sum / 2

    if len(results) > 1 and verbose:
        print(" Median: " + str(final_result))

    return(final_result)


def check_userns():
    proc_muns = "/proc/sys/user/max_user_namespaces"

    try:
        mf = open(proc_muns, mode='r')
        max_usrns = int(mf.read())
    except Exception:
        print("Cannot open/read from %s, assuming user namespace "
              "support disabled", proc_muns)
        return False

    mf.close()
    if max_usrns > 0:
        return True
    else:
        return False


# User namespace flag needed to support nested singularity
def get_usernamespace_flag(cec):
    if cec == "singularity":
        if check_userns():
            print("System supports user namespaces, enabling in "
                  "singularity call")
            return("-u ")

    return("")


def run_benchmark(benchmark, cm, output, verbose, conf):

    commands = {'docker': "docker run --rm --network=host -v " + output +
                ":/results ",
                'singularity': "singularity run -B " + output +
                ":/results " + get_usernamespace_flag(cm) + "docker://"}

    bench_conf = conf['benchmarks'][benchmark]
    bmark_keys = bench_conf.keys()
    bmk_options = {'debug': '-d', 'threads': '-t', 'events': '-e',
                   'copies': '-c'}
    options_string = ""

    runs = int(conf['repetitions'])
    log = output + "/" + conf['name'] + ".log"

    for option in bmk_options.keys():
        if option in bmark_keys and \
                str(bench_conf[option]) \
                not in ['None', 'False']:
            options_string = options_string + ' ' + bmk_options[option]
            if option != 'debug':
                options_string = options_string + ' ' + \
                    str(bench_conf[option])
    try:
        lfile = open(log, mode='a')
    except Exception:
        print("\nError: failure to open " + log)
        return(-1)

    benchmark_complete = conf['registry'] + '/' + benchmark +\
        ':' + bench_conf['version'] + options_string

    sys.stdout.write("Executing " + str(runs) + " run")
    if runs > 1:
        sys.stdout.write('s')
    sys.stdout.write(" of " + benchmark + "\n")

    command_string = commands[cm] + benchmark_complete
    command = command_string.split(' ')
    sys.stdout.write("Running  %s " % command)

    for i in range(runs):
        if verbose:
            sys.stdout.write('.')

        sys.stdout.flush()

        runstr = 'run' + str(i)

        bench_conf[runstr] = {}
        starttime = time.time()
        bench_conf[runstr]['start_at'] = time.ctime(starttime)
        try:
            cmdf = subprocess.Popen(command, stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT)
        except Exception:
            print("\nError: failure to execute: " + command_string)
            lfile.close()
            bench_conf['run' + str(i)]['end_at'] = \
                bench_conf['run' + str(i)]['start_at']
            bench_conf['run' + str(i)]['duration'] = 0
            proc_results(benchmark, output, verbose, conf)
            return(-1)

        line = cmdf.stdout.readline()
        while line:
            lfile.write(line)
            lfile.flush()
            line = cmdf.stdout.readline()

        cmdf.wait()

        endtime = time.time()
        bench_conf[runstr]['end_at'] = time.ctime(endtime)
        bench_conf[runstr]['duration'] = math.floor(endtime) - \
            math.floor(starttime)

        if cmdf.returncode != 0:
            print(("\nError: running " + benchmark + " failed.  Exit status " +
                  str(cmdf.returncode) + "\n"))

            if 'allow_fail' not in conf.keys() or conf['allow_fail'] is False:
                lfile.close()
                proc_results(benchmark, output, verbose, conf)
                return(-1)

    lfile.close()

    print("")

    result = proc_results(benchmark, output, verbose, conf)
    return(result)


def read_conf(cfile):

    global CONF

    print("Using custom configuration: " + cfile)

    try:
        yfile = open(cfile, mode='r')
        CONF = yfile.read()
    except Exception:
        print("\nError: cannot open/read from " + cfile + "\n")
        sys.exit(1)


def get_conf():
    global CONF
    return CONF


def parse_conf():

    base_keys = ['reference_machine', 'repetitions', 'method', 'benchmarks',
                 'name', 'registry']

    try:
        dat = yaml.safe_load(CONF)
    except Exception:
        print("\nError: problem parsing YAML configuration\n")
        sys.exit(1)

    try:
        for k in base_keys:
            val = dat['hepscore_benchmark'][k]
            if k == 'method':
                if val != 'geometric_mean':
                    print("Configuration error: only 'geometric_mean' method "
                          "is currently supported\n")
                    sys.exit(1)
            if k == 'registry':
                reg_string = dat['hepscore_benchmark']['registry']
                if not reg_string[0].isalpha() or reg_string.find(' ') != -1:
                    print("\nConfiguration error: illegal character in "
                          "registry")
                    sys.exit(1)
            if k == 'repetitions':
                try:
                    int(dat['hepscore_benchmark']['repetitions'])
                except ValueError:
                    print("\nConfiguration error: 'repititions' configuration "
                          "parameter must be an integer\n")
                    sys.exit(1)
    except KeyError:
        print("\nConfiguration error: " + k + " parameter must be specified")
        sys.exit(1)

    if 'scaling' in dat['hepscore_benchmark']:
        try:
            float(dat['hepscore_benchmark']['scaling'])
        except ValueError:
            print("\nConfiguration error: 'scaling' configuration parameter "
                  "must be an float\n")
            sys.exit(1)

    bcount = 0
    for benchmark in dat['hepscore_benchmark']['benchmarks'].keys():
        bmark_conf = dat['hepscore_benchmark']['benchmarks'][benchmark]
        bcount = bcount + 1

        if benchmark[0] == ".":
            print("\nINFO: the config has a commented entry " + benchmark +
                  " : Skipping this benchmark!!!!\n")
            dat['hepscore_benchmark']['benchmarks'].pop(benchmark, None)
            continue

        if not benchmark[0].isalpha() or benchmark.find(' ') != -1:
            print("\nConfiguration error: illegal character in " +
                  benchmark + "\n")
            sys.exit(1)

        if benchmark.find('-') == -1:
            print("\nConfiguration error: expect at least 1 '-' character in "
                  "benchmark name")
            sys.exit(1)

        bmk_req_options = ['version', 'scorekey']

        for k in bmk_req_options:
            if k not in bmark_conf.keys():
                print("\nConfiguration error: missing required benchmark "
                      "option -" + k)
                sys.exit(1)

        if 'refscore' in bmark_conf.keys():
            if bmark_conf['refscore'] is not None:
                try:
                    float(bmark_conf['refscore'])
                except ValueError:
                    print("\nConfiguration error: refscore is not a float")
                    sys.exit(1)
        if 'ref_scores' in bmark_conf.keys():
            for score in bmark_conf['ref_scores']:
                try:
                    float(bmark_conf['ref_scores'][score])
                except ValueError:
                    print("\nConfiguration error: ref_score " + score +
                          " is not a float")
                    sys.exit(1)

        if set(['refscore', 'ref_scores']).issubset(set(bmark_conf.keys())):
            print("\nConfiguration error: refscore and ref_scores cannot both "
                  "be specified")
            sys.exit(1)

    if bcount == 0:
        print("\nConfiguration error: no benchmarks specified")
        sys.exit(1)

    debug_print("The parsed config is:\n" +
                yaml.safe_dump(dat['hepscore_benchmark']), False)

    return(dat['hepscore_benchmark'])


def median_tuple(vals):

    sorted_vals = sorted(vals.items(), key=operator.itemgetter(1))

    med_ind = len(sorted_vals) / 2
    if len(sorted_vals) % 2 == 1:
        return(sorted_vals[med_ind][::-1])
    else:
        val1 = sorted_vals[med_ind - 1][1]
        val2 = sorted_vals[med_ind][1]
        return(((val1 + val2) / 2.0), (sorted_vals[med_ind - 1][0],
                                       sorted_vals[med_ind][0]))


def geometric_mean(results):

    product = 1
    for result in results:
        product = product * result

    return(product ** (1.0 / len(results)))


def main():

    global CONF, NAME, DEBUG

    allowed_methods = {'geometric_mean': geometric_mean}
    outfile = ""
    verbose = False
    cec = ""
    outobj = {}
    opost = "json"

    try:
        opts, args = getopt.getopt(sys.argv[1:], 'hpvVdsyf:o:')
    except getopt.GetoptError as err:
        print("\nError: " + str(err) + "\n")
        help()
        sys.exit(1)

    print_conf_and_exit = False
    for opt, arg in opts:
        if opt == '-h':
            help()
            sys.exit(0)
        if opt == '-p':
            print_conf_and_exit = True
        elif opt == '-v':
            verbose = True
        elif opt == '-V':
            verbose = True
            DEBUG = True
        elif opt == '-f':
            read_conf(arg)
        elif opt == '-y':
            opost = 'yaml'
        elif opt == '-o':
            outfile = arg
        elif opt == '-s' or opt == '-d':
            if cec:
                print("\nError: -s and -d are exclusive\n")
                sys.exit(1)
            if opt == '-s':
                cec = "singularity"
            else:
                cec = "docker"

    if print_conf_and_exit:
        print(yaml.safe_dump(yaml.safe_load(CONF)))
        sys.exit(0)

    if len(args) < 1:
        help()
        sys.exit(1)
    else:
        output = args[0]
        if not os.path.isdir(output):
            print("\nError: output directory must exist")
            sys.exit(1)

    output = output + '/' + NAME + '_' + time.strftime("%d%b%Y_%H%M%S")
    try:
        os.mkdir(output)
    except Exception:
        print("\nError: failed to create " + output)
        sys.exit(2)

    confobj = parse_conf()

# Creating a hash representation of the configuration object
# to be included in the final report
    m = hashlib.sha256()
    m.update(json.dumps(confobj, sort_keys=True))
    confobj['hash'] = m.hexdigest()

    sysname = ' '.join(os.uname())
    curtime = time.asctime()

    if cec and 'container_exec' in confobj:
        print("INFO: Overiding container_exec parameter on the commandline\n")
    elif not cec:
        if 'container_exec' in confobj:
            if confobj['container_exec'] == 'singularity' or \
                    confobj['container_exec'] == 'docker':
                cec = confobj['container_exec']
            else:
                print("\nError: container_exec config parameter must be "
                      "'singularity' or 'docker'\n")
                sys.exit(1)
        else:
            print("\nWarning: Run type not specified on commandline or in "
                  "config - assuming docker\n")
            cec = 'docker'

    confobj['environment'] = {'system': sysname, 'date': curtime,
                              'container_exec': cec}

    print(confobj['name'] + " Benchmark")
    print("Version: " + str(confobj['version']))
    print("System: " + sysname)
    print("Container Execution: " + cec)
    print("Registry: " + confobj['registry'])
    print("Output: " + output)
    print("Date: " + curtime + "\n")
    print("Hash: " + confobj['hash'] + "\n")

    confobj['wl-scores'] = {}

    results = []
    res = 0
    for benchmark in confobj['benchmarks']:
        res = run_benchmark(benchmark, cec, output, verbose, confobj)
        if res < 0:
            break
        results.append(res)

# Only compute a final score if all sub-benchmarks reported a score
    if res >= 0:
        method = allowed_methods[confobj['method']]
        fres = method(results)
        if 'scaling' in confobj.keys():
            fres = fres * confobj['scaling']

        print("\nFinal result: " + str(fres))
        confobj['score'] = fres
        confobj['status'] = "success"
    else:
        confobj['error'] = benchmark
        confobj['score'] = -1
        confobj['status'] = "failed"

    if not outfile:
        outfile = output + '/' + confobj['name'] + '.' + opost

    if opost == 'yaml':
        outobj['hepscore_benchmark'] = confobj
    else:
        outobj = confobj

    try:
        jfile = open(outfile, mode='w')
        if opost == 'yaml':
            jfile.write(yaml.safe_dump(outobj, encoding='utf-8',
                        allow_unicode=True))
        else:
            jfile.write(json.dumps(outobj))
        jfile.close()
    except Exception:
        print("\nError: Failed to create summary output " + outfile + "\n")
        sys.exit(2)

    if res < 0:
        sys.exit(2)


if __name__ == '__main__':
    main()
