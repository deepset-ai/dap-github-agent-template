import requests
import logging
from pathlib import Path
from typing import Dict, Optional, Tuple
import os

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# API configuration
API_URL = os.environ.get('DP_API_URL', 'https://api.cloud.deepset.ai')
API_KEY = os.environ.get('DP_API_KEY', '')


def load_yaml_file(file_path: Path) -> Optional[str]:
    """Load YAML file content if it exists."""
    if file_path.exists():
        return file_path.read_text()
    logger.warning(f"YAML file does not exist: {file_path}")
    return None


def yaml_has_changed(existing_yaml: str, new_yaml: str) -> bool:
    """Check if YAML content has changed."""
    return existing_yaml != new_yaml


def get_pipeline_yaml(workspace_name: str, pipeline_name: str) -> Tuple[bool, Optional[Dict]]:
    """Get pipeline YAML from deepset cloud. Returns (success, response_data)."""
    url = f"{API_URL}/api/v1/workspaces/{workspace_name}/pipelines/{pipeline_name}/yaml"

    headers = {
        "accept": "application/json",
        "authorization": f"Bearer {API_KEY}"
    }

    response = requests.get(url, headers=headers)

    if response.status_code == 200:
        return True, response.json()
    elif response.status_code == 404:
        logger.info(f"Pipeline {workspace_name}/{pipeline_name} does not exist in deepset Cloud")
        return False, None
    else:
        logger.error(f"Failed to get pipeline YAML: {response.text}")
        return False, None


def create_pipeline(workspace_name: str, query_yaml: str, indexing_yaml: str, pipeline_name: str) -> bool:
    """Create a new pipeline in deepset cloud."""
    url = f"{API_URL}/api/v1/workspaces/{workspace_name}/pipelines?dry_run=false"

    payload = {
        "deepset_cloud_version": "v2",
        "query_yaml": query_yaml,
        "indexing_yaml": indexing_yaml,
        "name": pipeline_name,
    }

    headers = {
        "accept": "application/json",
        "content-type": "application/json",
        "authorization": f"Bearer {API_KEY}"
    }

    response = requests.post(url, json=payload, headers=headers)

    if response.status_code in [200, 201]:
        logger.info(f"Successfully created pipeline {workspace_name}/{pipeline_name}")
        return True
    else:
        logger.error(f"Failed to create pipeline: {response.status_code} - {response.text}")
        return False


def update_pipeline(workspace_name: str, pipeline_name: str, query_yaml: str, indexing_yaml: str) -> bool:
    """Update an existing pipeline in deepset cloud."""
    url = f"{API_URL}/api/v1/workspaces/{workspace_name}/pipelines/{pipeline_name}/yaml"

    payload = {
        "deepset_cloud_version": "v2",
        "query_yaml": query_yaml,
        "indexing_yaml": indexing_yaml
    }

    headers = {
        "accept": "application/json",
        "content-type": "application/json",
        "authorization": f"Bearer {API_KEY}"
    }

    response = requests.put(url, json=payload, headers=headers)

    if response.status_code == 200:
        logger.info(f"Successfully updated pipeline {workspace_name}/{pipeline_name}")
        return True
    else:
        logger.error(f"Failed to update pipeline: {response.status_code} - {response.text}")
        return False


def process_local_pipeline(workspace: str, pipeline_name: str, query_yaml_path: Path, indexing_yaml_path: Path) -> bool:
    """Process a single pipeline from local files.

    Returns:
        bool: True if successful, False if any errors occurred
    """
    # Load local YAML files
    query_yaml = load_yaml_file(query_yaml_path)
    indexing_yaml = load_yaml_file(indexing_yaml_path)

    if not query_yaml:
        logger.error(f"Query YAML not found for {workspace}/{pipeline_name}. Skipping.")
        return False

    # If indexing YAML is not found, use a default empty pipeline
    if not indexing_yaml:
        logger.warning(f"Indexing YAML not found for {workspace}/{pipeline_name}. Using empty pipeline.")
        indexing_yaml = "# Empty Pipeline"

    # Check if pipeline exists in deepset Cloud
    exists, remote_data = get_pipeline_yaml(workspace, pipeline_name)

    if exists:
        # Compare local and remote YAMLs
        remote_query_yaml = remote_data.get("query_yaml", "")
        remote_indexing_yaml = remote_data.get("indexing_yaml", "")

        query_changed = yaml_has_changed(remote_query_yaml, query_yaml)
        indexing_changed = yaml_has_changed(remote_indexing_yaml, indexing_yaml)

        if not (query_changed or indexing_changed):
            logger.info(f"Neither query nor indexing pipeline for {workspace}/{pipeline_name} has changed. Skipping.")
            return True

        # Update pipeline if changes detected
        logger.info(f"Updating pipeline {workspace}/{pipeline_name} with local changes")
        return update_pipeline(workspace, pipeline_name, query_yaml, indexing_yaml)
    else:
        # Create new pipeline
        logger.info(f"Creating new pipeline {workspace}/{pipeline_name}")
        return create_pipeline(workspace, query_yaml, indexing_yaml, pipeline_name)


def main() -> int:
    """Main function to process all pipeline configurations in dist/pipelines.

    Returns:
        int: 0 if successful, 1 if any errors occurred
    """
    # Track if any errors occurred
    has_errors = False

    # Check if API token is available
    if not API_KEY:
        logger.error("DP_API_KEY environment variable is not set")
        return 1

    # Get the base directory for pipelines
    pipelines_dir = Path("dist") / "pipelines"

    if not pipelines_dir.exists():
        logger.error(f"Pipelines directory not found: {pipelines_dir}")
        return 1

    # Iterate through workspace directories
    for workspace_dir in pipelines_dir.iterdir():
        if not workspace_dir.is_dir():
            continue

        workspace_name = workspace_dir.name
        logger.info(f"Processing workspace: {workspace_name}")

        # Iterate through pipeline directories
        for pipeline_dir in workspace_dir.iterdir():
            if not pipeline_dir.is_dir():
                continue

            pipeline_name = pipeline_dir.name
            logger.info(f"Processing pipeline: {pipeline_name}")

            # Define paths to YAML files
            query_yaml_path = pipeline_dir / "query.yml"
            indexing_yaml_path = pipeline_dir / "indexing.yml"

            try:
                success = process_local_pipeline(workspace_name, pipeline_name, query_yaml_path, indexing_yaml_path)
                if not success:
                    has_errors = True
            except Exception as e:
                logger.error(f"Error processing pipeline {workspace_name}/{pipeline_name}: {str(e)}")
                has_errors = True

    if has_errors:
        logger.error("One or more errors occurred during processing")
        return 1
    else:
        logger.info("All pipelines processed successfully")
        return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())