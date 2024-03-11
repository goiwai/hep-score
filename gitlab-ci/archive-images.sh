#!/bin/bash

cd $CI_PROJECT_DIR

echo -e "\n---------------\nInstalling packages\n---------------\n"
yum install -y python3-pip sshpass
python3 -m pip install --upgrade pip 

cd $CI_PROJECT_DIR

pip3 install .

echo -e "\n---------------\nExecuting archive_images.py\n---------------\n"
python3 hepscore/archive_images.py -i ${default_config} -w ${workdir} -a ${ARCH} -r ${remote_archive}
STATUS=$?

ls -Rltrh ${workdir}

export HSVERSION=$(hepscore --version | awk '{print "hepscore_"$2}')
echo "HEPScore version: $HSVERSION"

if [ "$STATUS" == "111" ]; then
    echo "The archive already exists for the ${default_config} images"
elif [ "$STATUS" == "0" ]; then
    echo -e "\nUploading files"
    cat scp_command.sh
    source scp_command.sh || (echo "PROBLEM running scp command. Exit"; exit -1)
else
    echo "There was a problem"
    exit -1
fi

echo -e "\nCreating links"
cat ssh_command.sh
source ssh_command.sh || (echo "PROBLEM running ssh command. Exit"; exit -1)
