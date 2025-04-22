import requests
import os
import logging

from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def upload_custom_component():
    # Get environment variables or use default values
    api_url = os.environ.get('DP_API_URL', 'https://api.cloud.deepset.ai')
    api_key = os.environ.get('DP_API_KEY', '')

    # Construct the full URL
    url = f"{api_url}/api/v2/custom_components"

    # Set up headers
    headers = {
        'accept': 'application/json',
        'Authorization': f"Bearer {api_key}"
    }

    try:
        # Prepare the file to upload
        root_path = Path.cwd()
        with open(root_path / 'dist/components/custom_component.zip', 'rb') as file_data:
            files = {
                'file': ('custom_component.zip', file_data, 'application/zip')
            }

            # Make the POST request
            logger.info(f"Uploading custom component to {url}")
            response = requests.post(url, headers=headers, files=files)

            # Log response
            logger.info(f"Status Code: {response.status_code}")
            logger.info(f"Response: {response.text}")

            return response
    except FileNotFoundError:
        logger.error("File not found: dist/components/custom_component.zip")
        raise
    except requests.exceptions.RequestException as e:
        logger.error(f"Request failed: {e}")
        raise


if __name__ == "__main__":
    try:
        upload_custom_component()
    except Exception as e:
        logger.error(f"An error occurred: {e}")