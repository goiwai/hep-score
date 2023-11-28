#!/bin/bash -e

# This script is supposed to test the installation and execution of hepscore
# with the following scenarios (configurable via cli args)
# container_engine: singularity or docker
# container_uri: (only valid when running with singularity)
#                oras (i.e. sif images), 
#                docker (i.e. docker images), 
#                dir (i.e. cvmfs images)
# ncores: 
#          an integer (passed by --ncores arg)
#          "nproc"    (i.e. the runner core number passed by --ncores arg), 
#          "conf"     (i.e. use the value in the config file, without passing anything via cli)
#          "nproc_conf" (i.e. use the nproc value in the config file, without passing anything via cli)
#          "default"  (i.e. use the default value of the workloads, without passing anything via cli)
#
# The test is considered passed if the hepscore json report contains expected values for:
#          - container_engine
#          - registry uri
#          - configured number of cores
#          - score equal to configured number of cores (as reported by hello-world workloads) * scaling factor


function pretty_print(){
  Fname="ci_hello_world.sh"
  echo -e "\n------------------------------------------------------------------------------
[$Fname] $@
------------------------------------------------------------------------------\n"
}


[[ "$@" == "" ]] && pretty_print "Please pass cli arguments. Exiting" && exit 1

TEST_SEED=$RANDOM

INPUT_CNT_ENGINE=$1
INPUT_CNT_URI=$2
INPUT_NCORES=$3
HEPSCOREWD=$4

# Discover project dir
if [ -z $BASEDIR ]; then
    # go to project basedir
    cd "$(dirname $(readlink -f $0))/../.."
    BASEDIR=$(pwd)
fi

# Test configuration (singularity)
[ -z $BASECONF ] && BASECONF=$BASEDIR/hepscore/tests/etc/hepscore_conf_ci_helloworld.yaml

[ -z $HEPSCOREWD ] && HEPSCOREWD=/tmp/wd_${TEST_SEED}

[ ! -d "$HEPSCOREWD" ] && mkdir -p $HEPSCOREWD

# make a copy of the config
cp ${BASECONF} ${HEPSCOREWD}/hepscore_conf_ci_helloworld.yaml
HEPSCORECONF=${HEPSCOREWD}/hepscore_conf_ci_helloworld.yaml

chmod a+rw $HEPSCOREWD
pretty_print "variables \n
INPUT_CNT_ENGINE=${INPUT_CNT_ENGINE}
INPUT_CNT_URI=${INPUT_CNT_URI}
INPUT_NCORES=${INPUT_NCORES}
BASEDIR=${BASEDIR}
BASECONF=${BASECONF}
HEPSCORECONF=${HEPSCORECONF}
HEPSCOREWD=${HEPSCOREWD}
"

if [ ${INPUT_NCORES} == "nproc" ]; then
    NCORES=$(nproc)
    pretty_print "INPUT_NCORES is 'nproc'. Setting it to '${NCORES} and passing it to hepscore via cli'"
    ARGS_NCORE="--ncores ${NCORES}"
elif [ -z "${INPUT_NCORES//[0-9]*}" ]; then
    declare -i NCORES=${INPUT_NCORES}
    pretty_print "Passing to hepscore --ncores=${NCORES}"
    ARGS_NCORE="--ncores ${NCORES}"
elif [ ${INPUT_NCORES} == "conf" ]; then
    # use the ncores config in 
    # the hepscore config yaml file
    # cast to int to remove white spaces
    declare -i NCORES=$(grep "ncores" $HEPSCORECONF | cut -d: -f2 )
    pretty_print "INPUT_NCORES is 'conf'. Passing nothing to hepscore via cli"
    ARGS_NCORE=""
elif [ ${INPUT_NCORES} == "nproc_conf" ]; then
    # use the ncores config in 
    # the hepscore config yaml file
    # cast to int to remove white spaces
    #sed -e "s@^(\W*ncores\W*:\W*)([0-9]*)$@\1 $newvalue@" -i ${HEPSCORECONF}
    newvalue=$(nproc)
    sed -e "s@^\(\W*ncores\W*:\W*\)\([0-9]*\)\$@\1 $newvalue@" -i ${HEPSCORECONF}
    declare -i NCORES=$(grep "ncores" $HEPSCORECONF | cut -d: -f2 )
    pretty_print "INPUT_NCORES is 'nproc_in_conf'. Replacing ncores in the cfg file ${HEPSCORECONF}. Passing nothing to hepscore via cli"
    ARGS_NCORE=""
elif [ ${INPUT_NCORES} == "default" ]; then
    # use the default value of the workloads
    # that in this test is to saturate nproc
    pretty_print "INPUT_NCORES is 'default': removing ncores from the cfg file ${HEPSCORECONF}. Passing nothing to hepscore via cli"
    sed -e 's@^\W*ncores\W*:\W*[0-9]*$@@' -i ${HEPSCORECONF}
    ARGS_NCORE=""
else
    pretty_print "Input parameter INPUT_NCORES is not a valid one. Exiting." 
    exit 1
fi

penv=${HEPSCOREWD}/bmkenv_${TEST_SEED}
pretty_print "Install hepscore in python env  $penv"
python3 -m venv $penv
source $penv/bin/activate
pip3 install .

pretty_print "dump config ${HEPSCORECONF}"
cat ${HEPSCORECONF}

output_file="${HEPSCOREWD}/results.json"
pretty_print "output_file is ${output_file}"

hep-score -v \
    --container_uri ${INPUT_CNT_URI} \
    --container_exec ${INPUT_CNT_ENGINE} \
    ${ARGS_NCORE} \
    -f ${HEPSCORECONF} \
    -o $output_file ${HEPSCOREWD} 2>&1 #| tee  ${workdir}/outlog

#output_file=$(grep "Written output" ${HEPSCOREWD}/outlog | rev | cut -d ' ' -f1 | rev)
if [ ! -f ${output_file} ]; then
    pretty_print "Outputfile ${output_file} not found. FAIL"
    exit 1
fi

# Here starts the validation of the reported json
settings_container_exec=$(cat $output_file | jq --raw-output '.settings.container_exec')
settings_container_uri=$(cat $output_file  | jq -r '.settings.registry' | cut -d":" -f1)
settings_scaling=$(cat $output_file | jq --raw-output '.settings.scaling')
score=$(cat $output_file | jq --raw-output '.score')
config_hash=$(cat $output_file | jq --raw-output '.app_info.config_hash')

# Translate INPUT_NCORES} == "default" into the numeric value NCORES=nproc
[[ ${INPUT_NCORES} == "default" ]] && NCORES=$(nproc)
    
settings_ncores=$(cat $output_file | jq --raw-output '.settings.ncores')

# If settings_ncores == 0, assign the default nproc
[[ ${settings_ncores} -eq 0 ]] && settings_ncores=$(nproc)
validate_score=$(echo "$settings_scaling * $settings_ncores - $score" | bc)

pretty_print "Resumed table:
@ARCH=$(uname -m)
@INPUT_CNT_ENGINE=${INPUT_CNT_ENGINE}
@INPUT_CNT_URI=${INPUT_CNT_URI}
@INPUT_NCORES=${INPUT_NCORES}
@NCORES=${NCORES}
@HASH=${config_hash}
"

if [[ \
    ( ${validate_score} -eq 0 ) && \
    ( "${settings_ncores}" == ${NCORES} ) && \
    ( "${settings_container_exec}" == ${INPUT_CNT_ENGINE}) && \
    ( "${settings_container_uri}" == ${INPUT_CNT_URI})
    ]]; then
    pretty_print "!!!!!!Test passed!!!!!!"
else
    pretty_print "Test asserts False. Dumping result file and FAIL"
    cat $output_file | jq
    exit 1
    
fi
