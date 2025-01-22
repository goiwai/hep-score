import os
import json
import requests

# Configuration
ci_api_v4_url = os.getenv("CI_API_V4_URL")
ci_project_id = os.getenv("CI_PROJECT_ID")
ci_api_token = os.getenv("CI_API_TOKEN")
ci_commit_tag = os.getenv("CI_COMMIT_TAG")
ci_commit_tag_message = os.getenv("CI_COMMIT_TAG_MESSAGE", "No release notes.")

if not ci_commit_tag:
    raise ValueError("CI_COMMIT_TAG is not set.")

# Collect JSON data from files
assets_links = []
for filename in os.listdir():
    if filename.startswith("file_metadata") and filename.endswith(".json"):
        with open(filename, 'r') as f:
            try:
                data = json.load(f)
                if isinstance(data, dict):
                    assets_links.append(data)
                elif isinstance(data, list):  # If the file contains a list of dictionaries
                    assets_links.extend(data)
            except json.JSONDecodeError:
                print(f"Skipping invalid JSON file: {filename}")

# Prepare the data payload
payload = {
    "tag_name": ci_commit_tag,
    "name": ci_commit_tag,
    "description": ci_commit_tag_message,
    "assets": {
        "links": assets_links
    }
}

print(payload)

# API Endpoint
url = f"{ci_api_v4_url}/projects/{ci_project_id}/releases"

# Headers
headers = {
    "PRIVATE-TOKEN": ci_api_token,
    "Content-Type": "application/json"
}

# Make the POST request
try:
    response = requests.post(url, headers=headers, json=payload)
    response.raise_for_status()  # Raise an error for HTTP errors
    print("Release created successfully:")
    print(response.json())
except requests.exceptions.RequestException as e:
    print("Error while creating the release:")
    print(e)