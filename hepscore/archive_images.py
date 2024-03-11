"""
Script Description:
This script downloads SIF images specified in a YAML configuration file, 
archives them in a tar archive (no compression given that are SIF images), 
and prepares the scp and ssh commands to be executed in the CI for the upload
into the web archive.

Only image sets not already downloaded will be downloaded. 
A check of the sets already uploaded on the web archive is performed.

Hash representations of these sets are used for unique identification.

Usage:
python script_name.py -i <input_config> [-w <workdir>] [-a <architecture>] [-r <remote_archive_content>]
"""

import argparse
import subprocess
import yaml
import json
import os
import sys
import hashlib
import urllib.request
import shutil

def parse_yaml_file(input_config):
    """
    Parse a YAML configuration file.

    Args:
        input_config (str): Path to the input YAML configuration file.

    Returns:
        dict: Parsed YAML data.
    """

    with open(input_config, 'r') as file:
        data = yaml.safe_load(file)
    return data

def list_of_images(data, architecture=None):
    """
    Extract a list of images from the YAML data.

    Args:
        data (dict): Parsed YAML data.
        architecture (str, optional): Architecture type (e.g., x86_64, aarch64).

    Returns:
        tuple: A tuple containing a list of images and its hash.
    """

    local_images_list = []

    for key in data.keys():
        if key.startswith('hepscore'):
            benchmarks = data[key]['benchmarks']
            settings = data[key]['settings']
            break

    registry = ""
    for r in settings['registry']:
        if r.startswith("oras://"):
            registry = r
            break

    for key in benchmarks.keys():
        if key.startswith('.'):
            continue
        version = benchmarks[key]['version']

        if architecture is not None:
            local_images_list.append(f"{registry}/{key}:{version}_{architecture}")
        else:
            local_images_list.append(f"{registry}/{key}:{version}")

    # Sort the list to ensure consistent serialization
    sorted_images_list = sorted(local_images_list)
    print(f"sorted_images_list {sorted_images_list}")

    # Convert sorted list to JSON formatted string
    json_data = json.dumps(sorted_images_list)
    print(f"json_data of sorted_images_list {json_data}")

    # Generate a hash for the local images list
    hash_object = hashlib.sha256()
    hash_object.update(json_data.encode())
    images_list_hash = hash_object.hexdigest()

    print(f"Hash of local images list: {images_list_hash}")

    return local_images_list, images_list_hash

def download_images(images_list, directory, output_archive_file):
    """
    Download images from the provided list and archive them.

    Args:
        images_list (list): List of image URLs.
        directory (str): Directory to store downloaded images.
        output_archive_file (str): Path to the output archive file.
    """

    for image in images_list:
        # Download the image
        print(f"singularity pull --dir {directory} {image}")
        # Run the singularity command 
        sys.stdout.flush()  # Flush stdout to ensure immediate printing
        subprocess.run(["singularity", "pull", "--dir", directory, image], check=True)
        sys.stdout.flush()  # Flush stdout to ensure immediate printing

        # Print a message after the subprocess is completed
        print(f"Downloaded {image} successfully.")

        # Rename the downloaded image
        original_name=image.split('/')[-1].replace(":","_")+".sif"
        new_name=image.split('/')[-1]
        print(f"rename image from {directory}/{original_name} to {directory}/{new_name}")
        sys.stdout.flush()  # Flush stdout to ensure immediate printing
        subprocess.run(["mv", f"{directory}/{original_name}", f"{directory}/{new_name}"], check=True)

        # Add the image to the archive
        print(f"archive image {new_name} in {output_archive_file}")
        sys.stdout.flush()  # Flush stdout to ensure immediate printing
        subprocess.run(["tar", "-uvf", output_archive_file, "-C", directory, new_name], check=True)

        # Remove the downloaded image to save space
        print(f"free space removing downloaded image {directory}/{new_name}")
        sys.stdout.flush()  # Flush stdout to ensure immediate printing
        os.remove(f"{directory}/{new_name}")
        print(f"Removed {image} successfully.")


def download_and_validate_remote_images(remote_archive_url, local_hash):
    """
    Download and validate remote images.

    Args:
        remote_archive_url (str): URL to remote archive content (JSON).
        local_hash (str): Hash of local images list.

    Returns:
        dict: Dictionary containing remote images list.
    """

    remote_archive_url = remote_archive_url.rstrip('/')  # Remove trailing slashes if any
    remote_archive_url = f"{remote_archive_url}/{local_hash}/{local_hash}.json"

    try:
        with urllib.request.urlopen(remote_archive_url) as response:
            data = response.read().decode('utf-8')
            if response.status == 200:
                return json.loads(data)
            else:
                print(f"Warning: \n\tFailed to download remote archive from {remote_archive_url}.\n\tAssuming this archive is not available remotely.\n\tContinuing the archive process.")
                return {}  # Return an empty dictionary
    except urllib.error.URLError as e:
        print(f"Warning: \n\tFailed to download remote archive from {remote_archive_url}.\n\tError {e}.\n\tAssuming this archive is not available remotely.\n\tContinuing the archive process.")
        return {}  # Return an empty dictionary
    
def create_output_directory(directory):
    """
    Create an output directory if it doesn't exist.

    Args:
        directory (str): Directory path.
    """

    if not os.path.exists(directory):
        os.makedirs(directory)
        print(f"Directory '{directory}' created successfully.")
    elif len(os.listdir(directory)) > 0:
        print(f"Error: Directory '{directory}' is not empty.")
        sys.exit(1)

def generate_sha256sum(file_path):
    """
    Generate SHA256 hash for a file.

    Args:
        file_path (str): Path to the file.

    Returns:
        str: SHA256 hash of the file.
    """

    hash_sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_sha256.update(chunk)
    return hash_sha256.hexdigest()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Download images")
    parser.add_argument("-i", "--input_config", required=True, help="Path to input YAML configuration file")
    parser.add_argument("-w", "--workdir", default="hep-workloads-sif", help="Working directory to store intermediate files")
    parser.add_argument("-a", "--architecture", help="Architecture type (e.g., x86_64, aarch64)")
    parser.add_argument("-r", "--remote_archive_content", default=None, help="URL to remote archive content (JSON)")
    args = parser.parse_args()


    data = parse_yaml_file(args.input_config)
    local_images_list, local_images_hash = list_of_images(data, args.architecture)
    
    key_name=f"{args.architecture}_{local_images_hash}"
    archive_folder=os.path.join(args.workdir,key_name)
    create_output_directory(archive_folder)

    sif_image_folder=os.path.join(archive_folder,"sif_images")
    create_output_directory(sif_image_folder)


    output_archive_file=os.path.join(archive_folder,f"{key_name}.tar")
    output_archive_images=os.path.join(archive_folder,f"{key_name}.json")
    output_archive_sha256sum=os.path.join(archive_folder, f"{key_name}_sha256sum.txt")

    print("Output Archive File:", output_archive_file)
    print("Output Archive Images:", output_archive_images)
    print("Output Archive SHA256sum:", output_archive_sha256sum)

    must_download=False
    if args.remote_archive_content is not None:
        remote_images_list = download_and_validate_remote_images(args.remote_archive_content, key_name)
        if set(local_images_list) != set(remote_images_list):
            must_download=True
    else:
        must_download=True
    
    with open(output_archive_images, 'w') as f:
            json.dump(local_images_list, f)
    print(f"List of images saved in {output_archive_images}")
    print(f"{local_images_list}")

    with open("scp_command.sh", "w") as f:
        f.write("SSHPASS=${CI_CPUBMK} sshpass -v -e scp -v -oStrictHostKeyChecking=no -oPreferredAuthentications=keyboard-interactive -pr " +
                f"{archive_folder} cpubmk@lxplus.cern.ch:${{destination_folder}}/{key_name}\n")

    with open("ssh_command.sh", "w") as f:
        f.write('SSHPASS=${CI_CPUBMK} sshpass -v -e ssh -v -oStrictHostKeyChecking=no -oPreferredAuthentications=keyboard-interactive cpubmk@lxplus.cern.ch '+
            '"link_folder=${destination_folder}/../${HSVERSION}; [ ! -e \${link_folder} ] && mkdir \${link_folder}; ' +
            f'[ ! -e \${{link_folder}}/{key_name} ] && ln -s ${{destination_folder}}/{key_name} \${{link_folder}}/{key_name}" \n'
        )

    if must_download:
        download_images(local_images_list, sif_image_folder, output_archive_file)
        #create_tar_archive(archive_folder, output_archive_file)
        print(f"Images downloaded successfully in archive {output_archive_file}" )
        shutil.rmtree(sif_image_folder)
        print(f"Removed successfully temporarly {sif_image_folder} .")

        with open(output_archive_sha256sum, "w") as f:
            f.write(f"{key_name}.tar {generate_sha256sum(output_archive_file)}")
    else:
        print("Local and remote images are identical. No need to download.")
        sys.exit(111)
