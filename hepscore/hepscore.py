#!/usr/bin/python
###############################################################################
#
# hepscore.py - HEPscore benchmark execution
# Chris Hollowell <hollowec@bnl.gov>
#
#

import getopt
import glob
import json
import math
import os
import subprocess
import sys
import time
import yaml

NAME = "HEPscore"
VER = "0.63"
DEBUG = False

CONF = """
hepscore_benchmark:
  name: HEPscore19
  version: 0.31
  repetitions: 3  # number of repetitions of the same benchmark
  reference_machine: 'Intel Core i5-4590 @ 3.30GHz - 1 Logical Core'
  method: geometric_mean # or any other algorithm
  registry: gitlab-registry.cern.ch/hep-benchmarks/hep-workloads
  scaling: 10
  benchmarks:
    atlas-sim-bmk:
      version: v1.0
      scorekey: wl-scores
      ref_scores: { sim: 0.0052 }
    cms-reco-bmk:
      version: v1.0
      scorekey: wl-scores
      ref_scores: { reco: 0.1625 }
    lhcb-gen-sim-bmk:
      version: v0.12
      refscore: 7.1811
      scorekey: throughput_score
      subkey: 'GENSIM0 (evts per wall msec, including 1st evt)'
      debug: false
      events:
      threads:
"""


def help():

    global NAME

    namel = NAME.lower() + ".py"

    print(NAME + " Benchmark Execution - Version " + VER)
    print(namel + " {-s|-d} [-v] [-V] [-y] [-c NCOPIES] [-o OUTFILE] "
          "[-f CONF] OUTDIR")
    print(namel + " -h")
    print(namel + " -p [-f CONF]")
    print("Option overview:")
    print("-h           Print help information and exit")
    print("-v           Display verbose output, including all component "
          "benchmark scores")
    print("-d           Run benchmark containers in Docker")
    print("-s           Run benchmark containers in Singularity")
    print("-c           Set the sub-benchmark NCOPIES parameter (default: "
          "autodetect)")
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

    results = []
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

    gpaths = glob.glob(rpath + "/" + benchmark_glob + "*/*summary.json")

    debug_print("Looking for results in " + str(gpaths), False)
    i = 0
    for gpath in gpaths:
        debug_print("Opening file " + gpath, False)

        jfile = open(gpath, mode='r')
        line = jfile.readline()
        jfile.close()

        jscore = json.loads(line)
        try:
            bench_conf['run' + str(i)]['report'] = jscore
        except Exception:
            print('problem, bench_conf is %s' % json.dumps(bench_conf))
            raise
        try:
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
        except (KeyError, ValueError):
            if not fail:
                print("\nError: score not reported for one or more runs." +
                      "The retrieved json report contains\n%s" % jscore)
                fail = True

        i = i + 1

        if not fail:
            results.append(score)
            if verbose:
                print(" " + str(score))

    if fail:
        return(-1)

    if len(results) != runs:
        print("\nError: missing json score file for one or more runs")
        return(-1)

    final_result = median(results)

    if len(results) > 1 and verbose:
        print(" Median: " + str(final_result))

    return(final_result)


def get_image_path(registry,bmk_name,version):
    image = '%s/%s:%s' % (registry, bmk_name, version)
    return image.replace('//','/')

def run_workload(bmk_name, bmk_conf, outputdir, nruns=1, mode='docker',
                 registry='gitlab-registry.cern.ch/hep-benchmarks/hep-workloads',
                 verbose=False, glcopies=1):
    """Execute a specific reference workload.

    bmk_name   :   the bmk_name in the configuration
    bmk_conf   :   the specific configuration of a given workloads
                  as from config
    outputdir :   the output directory that is bind mount to the
                  dir /results in the container
    nruns     :   number of runs (default 1)
    mode      :   docker or singularity
    registry  :   image registry
    verbose   :   sets the debug verbosity of the wl container
    glcopies    : the number of copies of WL to be spawn 
                  defined at global level
    """
    print('bmk_name   : %s' % bmk_name)
    print('bmk_conf   : %s' % bmk_conf)
    print('outputdir : %s' % outputdir)
    print('nruns     : %s' % nruns)
    print('mode      : %s' % mode)
    print('registry  : %s' % registry)
    print('verbose   : %s' % verbose)
    print('copies    : %s' % glcopies)

    #benchmark_complete = 'registry + '/' + bmk_name +\
    #    ':' + bench_conf['version'] + options_string

    if 'version' in bmk_conf.keys():
        image_name = get_image_path(registry,bmk_name,bmk_conf['version'])
    else:
        print('Error: image version not specified')
        raise Exception

    # Retrieve the configuration specific to the benchmark
    print('bmk_conf is %s' % bmk_conf)
    options_string = check_bmk_options(bmk_conf, glcopies)
    
    for i in range(nruns):
        if verbose:
            sys.stdout.write('.')
            sys.stdout.flush()

        run_dir = outputdir + '/' + bmk_name + '/run_%d' %i
        print('run_dir is ' + run_dir)
        do_single_run(mode, image_name, options_string, run_dir)

def do_single_run(mode, image_name, options_string, run_dir):
    '''Execute the single run of a WL execution.

    Add start and end time in the directory, so that results can be generated again
    mode :
    image_name: 
    option_string:
    run_dir: 
    '''

    commands = {"docker":
                "docker run --rm --network=host -v %s:/results %s" % (run_dir,image_name),
                "singularity":
                "singularity run -B %s:/results docker://%s" % (run_dir,image_name)
            }


    log_file = run_dir + "/workload.stdout"

    #N.B. the -W forces the container to write in the speficied directory
    command_string = '%s -W %s' % (commands[mode], options_string)
    command = ' '.join(command_string.split()).split() # This is used to remove multiple whitespaces 
    print("Running  %s " % command)
    debug_print("Running %s\n" % command, True)
 
    starttime = time.time()
    try:
        #This is needed to store the log file in the same dir
        cmdf = subprocess.Popen(['mkdir', '-p', run_dir],
                                stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT)
        cmdf.wait()
        cmdf = subprocess.Popen(command, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT)
    except Exception as e:
        print("\nError: failure to execute: " + command_string)
        print(e)
        endtime = time.time()
        write_times(starttime, endtime, run_dir)
        return(-1)

    # store the stdout in a file in the same wl dir
    try:
        lfile = open(log_file, mode='a')
    except Exception:
        print("\nError: failure to open " + log_file)
        return(-1)

    line = cmdf.stdout.readline()
    while line:
        lfile.write(line)
        lfile.flush()
        line = cmdf.stdout.readline()

    cmdf.wait()
    lfile.close()
        
    # It is time to write the start and end time
    endtime = time.time()
    write_times(starttime, endtime, run_dir)

    if cmdf.returncode != 0:
        print(("\nError: running " + command_string +
               " failed.  Exit status " + str(cmdf.returncode) + "\n"))
        return -1

    return 0

def write_times(startime, endtime, run_dir):
    with open(run_dir + '/startime', 'w') as f:
        f.write('%s' % startime)
    with open(run_dir + '/endtime', 'w') as f:
        f.write('%s' % endtime)


def check_bmk_options(bmk_conf, glcopies):
    """check options and report the option string"""

    bmk_conf_keys = set(bmk_conf.keys())
    # Allowed options are
    bmk_allowed_options = {'debug': ('-d', bool),
                           'threads': ('-t', int),
                           'events': ('-e', int),
                           'copies': ('-c', int)}

    # is_number_of_copies_enforced = True
    options_string = ''
    for opt in sorted(set(bmk_allowed_options.keys()
                          ).intersection(bmk_conf_keys)):
        # check that the value matches the expected data type
        if type(bmk_conf[opt]) != bmk_allowed_options[opt][1]:
            continue
        # if the value is False, skip
        if bmk_conf[opt] is False:
            continue
        options_string = options_string + ' ' + bmk_allowed_options[opt][0]
        # if the type is not boolean append the  value
        if type(bmk_conf[opt]) != bool:
                options_string = options_string + ' ' + str(bmk_conf[opt])

    if 'copies' not in bmk_conf_keys and glcopies > 1:
        options_string = options_string + ' ' + '-c %d ' % glcopies

    return options_string


def run_benchmark(benchmark, cm, output, verbose, copies, conf):

    print('\nbenchmark is %s' % benchmark)
    print('\ncm %s' % cm)
    print('\noutput %s' % output)
    print('\nverbose %s' % verbose)
    print('\ncopies %s' % copies)
    print('\nconf %s\n' % conf)

    commands = {'docker': "docker run --rm --network=host -v " + output +
                ":/results ",
                'singularity': "singularity run -B " + output +
                ":/results docker://"}

    bench_conf = conf['benchmarks'][benchmark]
    bmark_keys = bench_conf.keys()
    bmk_options = {'debug': '-d', 'threads': '-t', 'events': '-e'}

    if copies != 1:
        options_string = " -c " + str(copies)
    else:
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

    debug_print("Running " + str(command), True)
    raise Exception  # FIXME
    for i in range(runs):
        if verbose:
            sys.stdout.write('.')
            sys.stdout.flush()

        runstr = 'run' + str(i)

        bench_conf[runstr] = {}
        starttime = time.time()
        bench_conf[runstr]['start_at'] = time.ctime(starttime)
        try:
            cmdf = subprocess.Popen(command,
                                    stdout=subprocess.PIPE,
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


def median(vals):

    if len(vals) == 1:
        return(vals[0])

    vals.sort()
    med_ind = len(vals) / 2
    if len(vals) % 2 == 1:
        return(vals[med_ind])
    else:
        return((vals[med_ind] + vals[med_ind - 1]) / 2.0)


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
    copies = 1
    opost = "json"

    try:
        opts, args = getopt.getopt(sys.argv[1:], 'hpvVdsyf:c:o:')
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
        elif opt == '-c':
            try:
                copies = int(arg)
            except ValueError:
                print("\nError: argument to -c must be an integer\n")
                sys.exit(1)
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

    if not cec:
        print("\nError: must specify run type (Docker or Singularity)\n")
        help()
        sys.exit(1)

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

    sysname = ' '.join(os.uname())
    curtime = time.asctime()

    confobj['environment'] = {'system': sysname, 'date': curtime,
                              'container_exec': cec, 'ncopies': copies}

    print(confobj['name'] + " Benchmark")
    print("Version: " + str(confobj['version']))
    if copies > 0:
        print("Sub-benchmark NCOPIES: " + str(copies))
    print("System: " + sysname)
    print("Container Execution: " + cec)
    print("Registry: " + confobj['registry'])
    print("Output: " + output)
    print("Date: " + curtime + "\n")

    results = []
    res = 0
    for benchmark in confobj['benchmarks'].keys():
        run_workload(benchmark, confobj['benchmarks'][benchmark], output,
                     nruns=confobj['repetitions'], mode=cec,
                     registry=confobj['registry'], verbose=verbose,
                     glcopies=copies)
        res = run_benchmark(benchmark, cec, output, verbose, copies, confobj)
        if res < 0:
            break
        results.append(res)

# Only compute a final score if all sub-benchmarks reported a score
    if res >= 0:
        method = allowed_methods[confobj['method']]
        fres = method(results) * confobj['scaling']

        print("\nFinal result: " + str(fres))
        confobj['score'] = fres
    else:
        confobj['ERROR'] = benchmark
        confobj['score'] = 'FAIL'

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
