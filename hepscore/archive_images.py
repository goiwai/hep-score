import argparse
import subprocess
import yaml
import json
import os
import sys
import hashlib
import urllib.request

def parse_yaml_file(input_config):
    with open(input_config, 'r') as file:
        data = yaml.safe_load(file)
    return data

def list_of_images(data, architecture=None):
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

    # Generate a hash for the local images list
    hash_object = hashlib.md5()
    hash_object.update(str(set(local_images_list)).encode())
    images_list_hash = hash_object.hexdigest()

    print(f"Hash of local images list: {images_list_hash}")

    return local_images_list, images_list_hash

def download_images(images_list, directory):
    for image in images_list:
        subprocess.run(["singularity", "pull", "--dir", directory, image], check=True)
        subprocess.run(["mv", directory+"/"+image.split('/')[-1].replace(":","_")+".sif", directory+"/"+image.split('/')[-1]], check=True)


def download_and_validate_remote_images(remote_archive_url, local_hash):
    remote_archive_url = remote_archive_url.rstrip('/')  # Remove trailing slashes if any
    remote_archive_url = f"{remote_archive_url}/{local_hash}"

    try:
        with urllib.request.urlopen(remote_archive_url) as response:
            data = response.read().decode('utf-8')
            if response.status == 200:
                return json.loads(data)
            else:
                print(f"Warning: Failed to download remote archive from {remote_archive_url}")
                return {}  # Return an empty dictionary
    except urllib.error.URLError as e:
        print(f"Error: {e}")
        return {}  # Return an empty dictionary
    
def create_output_directory(directory):
    if not os.path.exists(directory):
        os.makedirs(directory)
        print(f"Directory '{directory}' created successfully.")
    elif len(os.listdir(directory)) > 0:
        print(f"Error: Directory '{directory}' is not empty.")
        sys.exit(1)

def create_tar_archive(folder_to_archive, output_archive_file):
    subprocess.run(["tar", "-czf", f"{output_archive_file}", "-C", folder_to_archive, "."], check=True)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Download images")
    parser.add_argument("-i", "--input_config", required=True, help="Path to input YAML configuration file")
    parser.add_argument("-w", "--workdir", default="hep-workloads-sif", help="Working directory to store intermediate files")
    parser.add_argument("-a", "--architecture", help="Architecture type (e.g., x86_64, aarch64)")
    parser.add_argument("-r", "--remote_archive_content", default=None, help="URL to remote archive content (JSON)")
    args = parser.parse_args()


    data = parse_yaml_file(args.input_config)
    local_images_list, local_images_hash = list_of_images(data, args.architecture)
    
    archive_folder=os.path.join(args.workdir,local_images_hash)
    create_output_directory(archive_folder)

    output_archive_file=archive_folder+".tar.gz"
    output_archive_images=os.path.join(args.workdir,f"{local_images_hash}.json")

    must_download=False
    if args.remote_archive_content is not None:
        remote_images_list = download_and_validate_remote_images(args.remote_archive_content, local_images_hash)
        if set(local_images_list) != set(remote_images_list):
            must_download=True
        else:
            print("Local and remote images are identical. No need to download.")
            sys.exit(0)
    else:
        must_download=True
    
    if must_download:
        download_images(local_images_list, archive_folder)
        create_tar_archive(archive_folder, output_archive_file)
        with open(output_archive_images, 'w') as f:
            json.dump(local_images_list, f)

    print(f"Images downloaded successfully in archive {output_archive_file}" )
    print(f"List of images in {output_archive_images}")
