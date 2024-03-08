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
                print(f"Warning: \n\tFailed to download remote archive from {remote_archive_url}.\n\tAssuming this archive is not available remotely.\n\tContinuing the archive process.")
                return {}  # Return an empty dictionary
    except urllib.error.URLError as e:
        print(f"Warning: \n\tFailed to download remote archive from {remote_archive_url}.\n\tError {e}.\n\tAssuming this archive is not available remotely.\n\tContinuing the archive process.")
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

def generate_sha256sum(file_path):
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

    output_archive_file=f"{archive_folder}.tar.gz"
    output_archive_images=os.path.join(args.workdir,f"{key_name}.json")
    output_archive_sha256sum=os.path.join(args.workdir, f"{key_name}_sha256sum.txt")

    must_download=False
    if args.remote_archive_content is not None:
        remote_images_list = download_and_validate_remote_images(args.remote_archive_content, f"{key_name}.json")
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
        with open(output_archive_sha256sum, "w") as f:
            f.write(generate_sha256sum(output_archive_file))

    print(f"Images downloaded successfully in archive {output_archive_file}" )
    print(f"List of images in {output_archive_images}")
