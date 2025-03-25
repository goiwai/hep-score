#!/usr/bin/env python3

import re
from collections import defaultdict
import argparse
import glob

def main(input_pattern):
    print(f"Input files matching pattern '{input_pattern}'")
    input_files = glob.glob(input_pattern)
    for file in input_files:
        print(file)
    print("")
    hashes_dic = defaultdict(list)  # will collect rows for the same hash value
    conf_dic = defaultdict(set)  # will collect distinct conf names for the same hash
    confs = set()  # will collect distinct conf names

    fmtstringA="| {:<4} "
    fmtstringB = "| {:<15} | {:<15} | {:<10} | {:<10} | {:<10} | {:<70} | {:<40} |"
    fmtstring = fmtstringA + fmtstringB
    linestr = fmtstring.format("", "", "", "", "", "", "", "").replace(" ", "-")

    # Print table header
    print(fmtstring.format("k", "CNT_ENGINE", "ARCH", "CNT_URI", "NCORES", "value", "HASH", "FILE"))
    print(linestr)

    # Process each file using the provided input pattern
    for file in input_files:
        with open(file, 'r') as f:
            lines = f.readlines()
            parsed_values = {}
            for line in lines:
                match = re.match(r'@(\w+)\s*=\s*(.*)', line.strip())
                if match:
                    key, value = match.groups()
                    parsed_values[key] = value

            engine = parsed_values.get('INPUT_CNT_ENGINE', '')
            arch = parsed_values.get('ARCH', '')
            uri = parsed_values.get('INPUT_CNT_URI', '')
            conf_cores = parsed_values.get('INPUT_NCORES', '')
            cores = parsed_values.get('NCORES', '')
            hash_val = parsed_values.get('HASH', '')

            conf_dic[hash_val].add(conf_cores)
            confs.add(conf_cores)
            hashes_dic[hash_val].append(fmtstringB.format(engine, arch, uri, conf_cores, "(" + cores + ")", hash_val, file.split('/')[-1]))

    num = 1
    for aconf in confs:
        hashes = [k for k, v in conf_dic.items() if aconf in v]
        num_here = num
        for key in hashes:
            for line in hashes_dic[key]:
                print((fmtstringA + "{}").format(num, line))
                num += 1
            del hashes_dic[key]
            if num > num_here:
                print(linestr)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Process input files.')
    parser.add_argument('input_pattern', type=str, help='Pattern for input files')
    args = parser.parse_args()

    main(args.input_pattern)