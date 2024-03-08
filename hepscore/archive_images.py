import argparse
import subprocess
import yaml
import json
import requests
import os
import sys
import hashlib

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

    for key in benchmarks.keys():
        if benchmark_type.startswith('.'):
            continue
        version = benchmarks[key]['version']
        registry = ""
        for r in settings['registry']:
            if r.startswith("oras://"):
                registry = r
                break

        if architecture is not None:
            local_images_list.append(f"{registry}/{key}:{version}_{architecture}")
        else:
            local_images_list.append(f"{registry}/{key}:{version}")

    # Generate a hash for the local images list
    hash_object = hashlib.md5()
    print(str(set(local_images_list)))
    print(str(set(local_images_list)).encode())
    hash_object.update(str(set(local_images_list)).encode())
    images_list_hash = hash_object.hexdigest()

    return local_images_list, images_list_hash

def download_images(images_list, directory):
    for image in images_list:
        subprocess.run(["apptainer", "pull", "--dir", directory, image], check=True)
        subprocess.run(["mv", directory+"/"+image.split('/')[-1].replace(":","_")+".sif", directory+"/"+image.split('/')[-1]], check=True)


def download_and_validate_remote_images(remote_archive_url, local_hash):
    remote_archive_url = remote_archive_url.rstrip('/')  # Remove trailing slashes if any
    remote_archive_url = f"{remote_archive_url}/{local_hash}"

    response = requests.get(remote_archive_url)
    if response.status_code == 200:
        return json.loads(response.text)
    else:
        print(f"Error: Failed to download remote archive from {remote_archive_url}")
        sys.exit(1)

def create_output_directory(directory):
    if not os.path.exists(directory):
        os.makedirs(directory)
        print(f"Directory '{directory}' created successfully.")
    elif len(os.listdir(directory)) > 0:
        print(f"Error: Directory '{directory}' is not empty.")
        sys.exit(1)

def create_tar_archive(output_archive):
    subprocess.run(["tar", "-czf", f"{output_archive}.tar.gz", "-C", output_archive, "."], check=True)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Download images")
    parser.add_argument("input_config", help="Path to input YAML configuration file")
    parser.add_argument("output_archive", nargs="?", default="hep-workloads-sif", help="Path to output archive (JSON)")
    parser.add_argument("--architecture", help="Architecture type (e.g., x86_64, aarch64)")
    parser.add_argument("--remote_archive_content", default=None, help="URL to remote archive content (JSON)")
    args = parser.parse_args()

    create_output_directory(args.output_archive)

    data = parse_yaml_file(args.input_config)
    local_images_list, local_images_hash = list_of_images(data, args.architecture)

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
        download_images(local_images_list, args.output_archive)
        create_tar_archive(args.output_archive)
        with open(f"{local_images_hash}.json", 'w') as f:
            json.dump(local_images_list, f)

    print(f"Images downloaded successfully in archive {args.output_archive}.tar.gz" )
    print(f"List of images in {local_images_hash}.json")
