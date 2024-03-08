#!/bin/bash 

cd $CI_PROJECT_DIR
yum install -y python3-pip sshpass
python3 -m pip install --upgrade pip 
pip3 install .
python3 hepscore/archive_images.py -i ${default_config} -w ${workdir} -a ${ARCH} -r ${remote_archive}
STATUS=$?
ls -Rltrh ${workdir}
hepscore --version
HSVERSION=$(hepscore --version | awk '{print $2}')
echo "HEPScore version $HSVERSION"
if [ "$STATUS" == "111" ]; then
    echo "The archive already exists for the ${default_config} images"
elif [ "$STATUS" == "0" ]; then
    cat ${workdir}/*.json ; echo -e "\n"
    cat ${workdir}/*_sha256sum.txt ; echo -e "\n"

    archive_file=`ls ${workdir}/*tar.gz`
    echo $archive_file
    SSHPASS=${CI_CPUBMK} sshpass -v -e scp -v -oStrictHostKeyChecking=no -oPreferredAuthentications=keyboard-interactive \
    ${workdir}/*.tar.gz ${workdir}/*.json ${workdir}/*_sha256sum.txt cpubmk@lxplus.cern.ch:${destination_folder}
    curl -o retrieved_file ${remote_archive}/${archive_file}
    # - cmp retrieved_file ${archive_file}
else
    echo "There was a problem"
    exit -1
fi

