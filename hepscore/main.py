#!/usr/bin/env python3
"""HEPscore benchmark execution CLI tool

Copyright 2019-2021 CERN. See the COPYRIGHT file at the top-level directory
of this distribution. For licensing information, see the COPYING file at
the top-level directory of this distribution.
"""


import argparse
import logging
import os
import sys
import textwrap
import time
import yaml
import hepscore.hepscore as hepscore

logger = logging.getLogger()


def parse_args(args):

    """Parse passed argv list."""
    parser = argparse.ArgumentParser(
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=textwrap.dedent('''
        -----------------------------------------------
        HEPscore Benchmark Execution
        -----------------------------------------------
        This utility orchestrates several benchmarks

        Additional Information:
           https://gitlab.cern.ch/hep-benchmarks/hep-score
        Contact:
           https://wlcg-discourse.web.cern.ch/c/hep-benchmarks
        '''), epilog=textwrap.dedent('''
        -----------------------------------------------
        Examples:

        Run benchmarks via Docker, and display verbose information:
        $ hep-score -v -m docker ./testdir

        Run using Singularity (default) with a custom benchmark configuration:
        $ hep-score -f /tmp/my-custom-bmk.yml /tmp

        List built-in benchmark configurations:
        $ hep-score -l

        Run with a specified built-in benchmark configuration:
        $ hep-score -n hepscore-testkv /tmp

        Included benchmark configuraton files available in:
        ''' + hepscore.config_path)
    )

    # required argument
    parser.add_argument("OUTDIR", type=str, nargs='?', help="Base output directory.")
    # optionals
    parser.add_argument("-m", "--container_exec", choices=['singularity', 'docker'],
                        nargs='?', default=False,
                        help="specify container platform for benchmark execution "
                             "(singularity [default], or docker).")
    parser.add_argument("-i", "--container_uri", choices=['docker', 'shub', 'dir', 'oras', 'https'],
                        nargs='?', default=False,
                        help="specify container registry type "
                             "(oras, docker, shub, dir, https).")
    parser.add_argument("-S", "--userns", action='store_true',
                        help="enable user namespace for Singularity, if supported.")
    parser.add_argument("-c", "--clean", action='store_true',
                        help="clean residual container images from system after run.")
    parser.add_argument("-C", "--clean_files", action='store_true',
                        help="clean residual files & directories after execution. Tar results.")
    parser.add_argument("-f", "--conffile", nargs='?', default='',
                        help="custom config yaml to use instead of default.")
    parser.add_argument("-l", "--list", action='store_true',
                        help="list built-in benchmark configurations and exit.")
    parser.add_argument("-n", "--namedconf", nargs='?', default='',
                        help="use specified named built-in benchmark configuration.")
    parser.add_argument("-r", "--replay", action='store_true',
                        help="replay output using existing results directory OUTDIR.")
    parser.add_argument("-o", "--outfile", nargs='?', default=False,
                        help="specify summary output file path/name.")
    parser.add_argument("-y", "--yaml", action='store_true',
                        help="create YAML summary output instead of JSON.")
    parser.add_argument("-p", "--print", action='store_true',
                        help="print configuration and exit.")
    parser.add_argument("-V", "--version", action='version',
                        version="%(prog)s " + hepscore.__version__)
    parser.add_argument("-v", "--verbose", action='store_true',
                        help="enables verbose mode. Display debug messages.")

    arg_dict = vars(parser.parse_args(args))

    if arg_dict['OUTDIR'] is None and not (arg_dict['print'] or arg_dict['list']):
        print("Output directory required. 'hep-score <args> OUTDIR\n"
              "See usage: 'hep-score --help'")
        sys.exit(2)

    return arg_dict


def main():
    """Command-line entry point. Parses arguments to construct configuration dict."""
    args = parse_args(sys.argv[1:])
    default_config = hepscore.config_path + "/hepscore-default.yaml"

    user_args = {k: v for k, v in args.items() if v is not False}
    vstring = ' '
    vlevel = logging.INFO
    if 'verbose' in user_args:
        vstring = '.%(funcName)s() '
        vlevel = logging.DEBUG
    logging.basicConfig(format='%(asctime)s hepscore' + vstring + '[%(levelname)s] %(message)s',
                        datefmt='%Y-%m-%d %H:%M:%S', level=vlevel)

    if args['list']:
        print("Available built-in HEPscore benchmark configurations:")
        for f in hepscore.list_named_confs():
            print(f)
        sys.exit(0)

    if args['conffile']!='' and args['namedconf']!='':
        logger.error('Cannot specify both a configuration file and a built-in configuration')
        sys.exit(1)

    if args['conffile']!='':
        conffile = args.pop('conffile')
    elif args['namedconf']!='':
        if args['namedconf'] not in hepscore.list_named_confs():
            logging.error("%s not an available built-in configuration", args['namedconf'])
        conffile = hepscore.named_conf(args.pop('namedconf'))
    else:
        conffile = default_config

    active_config = hepscore.read_yaml(conffile)

    if args['print']:
        print(yaml.safe_dump(active_config, sort_keys=False))
        sys.exit(0)

    # Don't let users pass their dirs in conf object
    outdir = args.pop('OUTDIR', None)

    usekey = None
    for bmkey in ['hepscore', 'hepscore_benchmark']:
        if bmkey in active_config:
            usekey = bmkey
            break
    if usekey is None:
        print("Required 'hepscore' key not in configuration!")
        sys.exit(1)

    # separate containment overide from options
    if args['container_exec']:
        active_config[usekey]['settings']['container_exec'] \
            = args.pop('container_exec')

    outtype = 'yaml' if 'yaml' in user_args else 'json'
    user_args.pop('yaml', None)

    # Populate active config with cli override
    if 'options' not in active_config['hepscore']:
        active_config[usekey]['options'] = {}
    for arg in user_args:
        active_config[usekey]['options'][arg] = user_args[arg]


    # check replay outdir actually contains a run...
    if args['replay']:
        if not os.path.isdir(outdir):
            print("Replay did not find a valid directory at " + outdir)
            sys.exit(1)
        else:
            resultsdir = outdir
    else:
        try:
            resultsdir = os.path.join(outdir, hepscore.HEPscore.__name__ + '_' + \
                time.strftime("%d%b%Y_%H%M%S"))
            os.makedirs(resultsdir)
        except NotADirectoryError:
            logger.error("%s not valid directory", resultsdir)
            sys.exit(1)
        except PermissionError:
            logger.error("Failed creating output directory %s. Do you have write permission?",
                         resultsdir)
            sys.exit(1)

    hep_score = hepscore.HEPscore(active_config, resultsdir)

    if hep_score.run(args['replay']) >= 0:
        hep_score.gen_score()
    hep_score.write_output(outtype, args['outfile'])


if __name__ == '__main__':
    main()
