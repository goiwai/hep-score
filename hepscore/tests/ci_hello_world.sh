#!/bin/bash -e

function run_test(){
    echo "[ci_hello_world.sh] running run_test $@"
    config=$1
    workdir=$2
    shift
    shift
    [[ "$@" != "" ]] && options=" $@ " 
    echo "[ci_hello_world.sh] dump config $config"
    cat $config

    hep-score $options -v -f $config $workdir 2>&1 | tee  ${workdir}/outlog

    output_file=$(grep "Written output" ${HEPSCOREWD}/outlog | rev | cut -d ' ' -f1 | rev)
    echo "[ci_hello_world.sh] output_file is ${output_file}"
    validate=$(cat $output_file | jq '.settings.ncores * .settings.scaling == .score')
    if [ "$validate" == "false" ]; then
        echo -e "\n@@@@@@@@@@@@@@@@@\n [ci_hello_world.sh] results does not scale with cores. Dumping result file and FAIL\n@@@@@@@@@@@@@@@@@\n"
        cat $output_file | jq
        exit 1
    else
        echo -e "\n@@@@@@@@@@@@@@@@@\n [ci_hello_world.sh] Test passed \n@@@@@@@@@@@@@@@@@\n"
    fi
}

function test_ncores(){
    config=$1
    workdir=$2

    echo -e "\n@@@@@@@@@@@@@@@@@\n [ci_hello_world.sh] Number of cores defined in settings\n@@@@@@@@@@@@@@@@@\n"
    run_test $config $workdir

    echo -e "\n@@@@@@@@@@@@@@@@@\n Number of cores defined via command line\n@@@@@@@@@@@@@@@@@\n"
    run_test $config $workdir  '--ncores 2'

}

echo "[ci_hello_world.sh] HEPSCORECONF ${HEPSCORECONF}"
echo "[ci_hello_world.sh] HEPSCORECONF_DOCKER ${HEPSCORECONF_DOCKER}"
cat ${HEPSCORECONF} | sed -e "s@addarch: true@addarch: false@" -e "s@container_uri: oras@container_uri: docker@" > ${HEPSCORECONF_DOCKER}

echo -e "\n@@@@@@@@@@@@@@@@@\n [ci_hello_world.sh] Run with Apptainer on sif images\n@@@@@@@@@@@@@@@@@\n "
test_ncores ${HEPSCORECONF} ${HEPSCOREWD}


echo -e "\n@@@@@@@@@@@@@@@@@\n [ci_hello_world.sh] Run with Apptainer on docker images\n@@@@@@@@@@@@@@@@@\n "
test_ncores ${HEPSCORECONF_DOCKER} ${HEPSCOREWD}

# echo "Run with Docker on docker images"
# sed -i ${HEPSCORECONF_DOCKER} -e "s@container_exec: singularity@container_exec: docker@"
# cat ${HEPSCORECONF_DOCKER}
# hep-score -v -f ${HEPSCORECONF_DOCKER} ${HEPSCOREWD}

    # - echo "Run with singularity on cvmfs images"
    # - | 
    #   sed -i ${HEPSCORECONF} -e "s@container_uri: oras@container_uri: dir@"
    # - cat ${HEPSCORECONF}
    # - hep-score -v -f ${HEPSCORECONF} $CI_PROJECT_DIR/hepscore/tests/data/HEPscore_ci/