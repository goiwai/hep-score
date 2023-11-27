#!/bin/bash

# Print table header
echo "CNT_ENGINE|ARCH|CNT_URI| NCORES|value|HASH" | \
    awk -F'|' 'END{ 
                printf "| %-15s | %-15s | %-10s | %-10s | %-10s | %-70s |\n", $1, $2, $3, $4 , "("$5")", $6
            }'> intermediate_out_file.txt

# Process each file
for file in `ls helloworld_out_*.log`; do
    awk -F'=' '/@ARCH/{ arch=$2 }
        /@INPUT_CNT_ENGINE/{ engine=$2 } 
        /@INPUT_CNT_URI/{ uri=$2 } 
        /@INPUT_NCORES/{ ncores=$2 } 
        /@NCORES/{ cores=$2 } 
        /@HASH/{ hash=$2 } 
        END{ printf "| %-15s | %-15s | %-10s | %-10s | %-10s | %-70s |\n", engine, arch, uri, ncores,"("cores")", hash}' "$file"
done >> intermediate_out_file.txt

python3 -c '
from collections import defaultdict

hashes_dic = defaultdict(list)  # will collect rows for same hash value
conf_dic = defaultdict(set) # will collect distinct conf names for same hash
confs = set() # will collect distinct conf names

linestr = "| {:<4} | {:<15} | {:<15} | {:<10} | {:<10} | {:<10} | {:<70} |".format("", "", "", "", "", "", "").replace(" ", "-")

with open("intermediate_out_file.txt", "r") as afile:
    lines = afile.readlines()
    for index, line in enumerate(lines):
        if index == 0:
            print("| {:<4} {}".format("k",line.strip()))
            print(linestr)
        else:
            #print(line)
            parts = line.strip().split("|")[1:-1]
            parts = [part.strip() for part in parts]
            #print(parts)
            hash=parts[-1]
            conf=parts[3]
            hashes_dic[hash].append(line.strip())
            conf_dic[hash].add(conf)
            confs.add(conf)
            #print(hashes_dic[hash] )
            
    #print(conf_dic)
    #print(confs)
    num=1
    for aconf in confs:
        #print(aconf)
        hashes = [k for k,v in conf_dic.items() if aconf in v]
        num_here=num
        for key in hashes:
            #print(hashes_dic[key])
            for line in hashes_dic[key]:
                print("| {:<4} {}".format(num,line))
                num+=1
            del(hashes_dic[key])
            if num > num_here: print(linestr)
' | tee test_summary_table.txt
