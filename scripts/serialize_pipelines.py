import yaml
import logging
from pathlib import Path
from typing import Dict, Optional, Any

from haystack import Pipeline
from dotenv import load_dotenv

load_dotenv()

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def load_yaml_if_exists(file_path: Path) -> Optional[str]:
    """
    Load YAML file content if it exists.

    :param file_path: Path to the YAML file
    :return: Content of the YAML file if it exists, None otherwise
    """
    if file_path.exists():
        return file_path.read_text()
    return None


def save_yaml(file_path: Path, content: str) -> None:
    """
    Save YAML content to file.

    :param file_path: Path where the YAML file should be saved
    :param content: YAML content to save
    """
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(content)
    logger.info(f"Saved YAML to: {file_path}")


def yaml_has_changed(existing_yaml: Optional[str], new_yaml: str) -> bool:
    """
    Check if YAML content has changed.

    :param existing_yaml: Current content of the YAML file, if it exists
    :param new_yaml: New content to compare against
    :return: True if the content has changed or the file doesn't exist, False otherwise
    """
    if existing_yaml is None:
        return True
    return existing_yaml != new_yaml


def prepare_yaml_string(pipeline: Optional[Pipeline]) -> str:
    """
    Convert a pipeline object to a YAML string.

    :param pipeline: The pipeline object to convert or None
    :return: The YAML representation of the pipeline
    """
    if pipeline is None:
        return "# Empty Pipeline"

    # Handle dAP specific additions to Haystack pipeline yaml
    inputs = pipeline.metadata.get("inputs", {})
    outputs = pipeline.metadata.get("outputs", {})

    pipeline_yaml = pipeline.dumps()

    pipeline_yaml_dict = yaml.safe_load(pipeline_yaml)
    pipeline_yaml_dict["inputs"] = inputs
    pipeline_yaml_dict["outputs"] = outputs

    return yaml.dump(pipeline_yaml_dict, default_flow_style=False)


def process_pipeline(pipeline_dict: Dict[str, Any]) -> bool:
    """Process a single pipeline configuration and return whether any files were changed.

    :param pipeline_dict: Dictionary containing pipeline configuration
    :return: True if any files were changed, False otherwise
    """
    workspace = pipeline_dict["workspace"]
    name = pipeline_dict["name"]

    query_pipeline = pipeline_dict["query"]
    indexing_pipeline = pipeline_dict.get("indexing", None)

    query_yaml = prepare_yaml_string(query_pipeline)
    indexing_yaml = prepare_yaml_string(indexing_pipeline)

    dist_dir = Path("dist") / "pipelines" / workspace / name
    query_yaml_path = dist_dir / "query.yml"
    indexing_yaml_path = dist_dir / "indexing.yml"

    existing_query_yaml = load_yaml_if_exists(query_yaml_path)
    existing_indexing_yaml = load_yaml_if_exists(indexing_yaml_path)

    query_changed = yaml_has_changed(existing_query_yaml, query_yaml)
    indexing_changed = yaml_has_changed(existing_indexing_yaml, indexing_yaml)

    if not (query_changed or indexing_changed):
        logger.info(f"Neither query nor indexing pipeline for {workspace}/{name} has changed. Skipping.")
        return False

    save_yaml(query_yaml_path, query_yaml)
    save_yaml(indexing_yaml_path, indexing_yaml)

    logger.info(f"Successfully processed pipeline for {workspace}/{name}")
    return True


def main() -> bool:
    """Main function to process all pipeline configurations.

    :return: True if any files were changed, False otherwise
    """
    # Import pipeline configurations from dc_custom_component.pipelines
    from dc_custom_component.pipelines import dp_pipelines
    any_errors = False

    # Process each import
    for pipeline_config in dp_pipelines:
        try:
            process_pipeline(pipeline_config)
        except Exception as e:
            logger.error(f"Error processing pipeline {pipeline_config.get('name', 'unknown')}: {str(e)}")
            any_errors = True

    return any_errors


if __name__ == "__main__":
    errors = main()
    # Exit with status code 1 if changes were made, so the GitHub Action knows to commit them
    if errors:
        exit(1)
    exit(0)