#!/usr/bin/env python3
###############################################################################
# Copyright 2019-2020 CERN. See the COPYRIGHT file at the top-level directory
# of this distribution. For licensing information, see the COPYING file at
# the top-level directory of this distribution.
###############################################################################
#
# main.py - HEPscore benchmark execution CLI tool
#

import argparse
import logging
from pathlib import Path
import sys
import textwrap
import time
import yaml
from hepscore.hepscore import HEPscore, __version__

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
        Contact: benchmark-suite-wg-devel@cern.ch
        '''), epilog=textwrap.dedent('''
        -----------------------------------------------
        Examples:

        Run benchmarks via Docker, and display verbose information:
        $ hep-score -v -m docker /tmp/rundir

        Run using Singularity (default) with a custom benchmark configuration:
        $ hep-score -f /tmp/my-custom-bmk.yml /tmp/hsresults
        ''')
    )

    default_config = Path(__file__).parent.joinpath('etc', 'hepscore-default.yaml')
    # required argument
    parser.add_argument("OUTDIR", type=str, nargs='?', help="Base output directory.")
    # optionals
    parser.add_argument("-m", "--container_exec", choices=['singularity', 'docker'],
                        nargs='?', default=False,
                        help="specify container platform for benchmark execution "
                             "(singularity [default], or docker).")
    parser.add_argument("-S", "--userns", action='store_true',
                        help="enable user namespace for Singularity, if supported.")
    parser.add_argument("-c", "--clean", action='store_true',
                        help="clean residual container images from system after run.")
    parser.add_argument("-C", "--cleanall", action='store_true',
                        help="clean residual files & directories after execution. Tar results.")
    parser.add_argument("-f", "--conffile", nargs='?', default=default_config,
                        help="custom config yaml to use instead of default.")
    parser.add_argument("-r", "--replay", action='store_true',
                        help="replay output using existing results directory OUTDIR.")
    parser.add_argument("-o", "--outfile", nargs='?', default=False,
                        help="specify custom output filename. Default: HEPscore20.json.")
    parser.add_argument("-y", "--yaml", action='store_true',
                        help="YAML output instead of JSON.")
    parser.add_argument("-p", "--print", action='store_true',
                        help="print configuration and exit.")
    parser.add_argument("-V", "--version", action='version',
                        version="%(prog)s " + __version__)
    parser.add_argument("-v", "--verbose", action='store_true',
                        help="enables verbose mode. Display debug messages.")

    ns = parser.parse_args(args)
    nsd = vars(ns)

    if nsd['OUTDIR'] is None and nsd['print']==False:
        print("Output directory required. 'hep-score <args> OUTDIR\n"
              "See usage: 'hep-score --help'")
        sys.exit(2)

    return nsd


def main():
    """Command-line entry point."""
    args = parse_args(sys.argv[1:])

    user_args = {k: v for k, v in args.items() if v is not False}
    vstring = ' '
    vlevel = logging.INFO
    if 'verbose' in user_args:
        vstring = '.%(funcName)s() '
        vlevel = logging.DEBUG
    logging.basicConfig(format='%(asctime)s hepscore' + vstring + '[%(levelname)s] %(message)s',
                        datefmt='%Y-%m-%d %H:%M:%S', level=vlevel)

    # Read config yaml
    try:
        with open(args['conffile'], 'r') as yam:
            active_config = yaml.safe_load(yam)
            args.pop('conffile', None)
    except Exception as e:
        print(e)
        logger.error("Cannot read/parse YAML configuration file %s", args['conffile'])
        sys.exit(1)
    if args['print']:
        print(yaml.safe_dump(active_config, sort_keys=False))
        sys.exit(0)

    # Don't let users pass their dirs in conf object
    resultsdir = Path(args.pop('OUTDIR', None))

    # separate conainment overide from options
    if args['container_exec']:
        active_config['hepscore_benchmark']['settings']['container_exec'] \
            = args.pop('container_exec')

    outtype = 'yaml' if 'yaml' in user_args else 'json'
    user_args.pop('yaml', None)

    # Populate active config with cli override
    if 'options' not in active_config['hepscore_benchmark']:
        active_config['hepscore_benchmark']['options'] = {}
    for arg in user_args:
        active_config['hepscore_benchmark']['options'][arg] = user_args[arg]


    # check replay outdir actually contains a run...
    if args['replay']:
        if not resultsdir.is_dir():
            logger.critical("Replay did not find a valid directory at %s", resultsdir)
            sys.exit(1)
    else:
        try:
            resultsdir = Path(resultsdir, HEPscore.__name__ + '_' + time.strftime("%d%b%Y_%H%M%S"))
            resultsdir.mkdir(parents=True)
        except OSError:
            logger.critical("Failed creating output directory %s. Do you have write permission?",
                            resultsdir)
            sys.exit(1)

    hs = HEPscore(active_config, resultsdir)

    if hs.run(args['replay']) >= 0:
        hs.gen_score()
    hs.write_output(outtype, args['outfile'])


if __name__ == '__main__':
    main()
