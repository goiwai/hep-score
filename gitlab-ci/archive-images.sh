#!/bin/bash 

cd $CI_PROJECT_DIR

echo -e "\n---------------\nInstalling packages\n---------------\n"
yum install -y python3-pip sshpass
python3 -m pip install --upgrade pip 
pip3 install .

echo -e "\n---------------\nExecuting archive_images.py\n---------------\n"
python3 hepscore/archive_images.py -i ${default_config} -w ${workdir} -a ${ARCH} -r ${remote_archive}
STATUS=$?
ls -Rltrh ${workdir}
HSVERSION=$(hepscore --version | awk '{print $2}')
echo "HEPScore version: $HSVERSION"
echo "Images in config file ${default_config} :"
JSONFile=$(find $workdir -name "*.json" -exec basename {} \;)
echo "JSONFile= $JSONFile"
cat ${workdir}/${JSONFile} ; echo -e "\n"

if [ "$STATUS" == "111" ]; then
    echo "The archive already exists for the ${default_config} images"
elif [ "$STATUS" == "0" ]; then
    cat ${workdir}/*_sha256sum.txt ; echo -e "\n"

    archive_file=`ls ${workdir}/*tar.gz`
    echo $archive_file
    SSHPASS=${CI_CPUBMK} sshpass -v -e scp -v -oStrictHostKeyChecking=no -oPreferredAuthentications=keyboard-interactive \
    ${workdir}/*.tar.gz ${workdir}/*.json ${workdir}/*_sha256sum.txt cpubmk@lxplus.cern.ch:${destination_folder}
    #curl -o retrieved_file ${remote_archive}/${archive_file}
    # - cmp retrieved_file ${archive_file}
else
    echo "There was a problem"
    exit -1
fi

echo "creating links"
SSHPASS=${CI_CPUBMK} sshpass -v -e ssh -oStrictHostKeyChecking=no -oPreferredAuthentications=keyboard-interactive \
    cpubmk@lxplus.cern.ch "[ ! -e ${destination_folder}/../${HSVERSION} ] && mkdir ${destination_folder}/../${HSVERSION} && ln -s ${destination_folder}/${JSONFile} ${destination_folder}/../${HSVERSION}/${JSONFile}" 