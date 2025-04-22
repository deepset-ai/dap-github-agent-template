import os
import shutil
import fnmatch
import zipfile
import logging
from pathlib import Path
from typing import List, Optional

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)


def create_zip_file(components_dir: Path, about_init_dir: Path, output_zip: Path, project_root: Path,
                    exclude_patterns: Optional[List[str]] = None) -> bool:
    """
    Create a zip file with the following structure:
    - pyproject.toml (at root)
    - src/dc_custom_component/components/ (all files from components_dir)
    - src/dc_custom_component/__about__.py
    - src/dc_custom_component/__init__.py
    While applying exclude patterns to filter unwanted files.
    """

    if exclude_patterns is None:
        exclude_patterns = [
            '*.env',
            '*venv*',
            '*.pyc',
            '__pycache__/*',
            '*.pyo',
            '.git/*',
            '.gitignore',
            '.DS_Store'
        ]

    components_path = Path(components_dir)
    about_init_path = Path(about_init_dir)
    output_path = Path(output_zip)
    root_path = Path(project_root)

    # Check if source directories exist
    if not components_path.exists():
        logging.error(f"Components directory does not exist: {components_path}")
        return False

    if not about_init_path.exists():
        logging.error(f"Custom component directory does not exist: {about_init_path}")
        return False

    # Count the files in the components directory
    files_count: int = sum(1 for _ in components_path.glob('**/*') if _.is_file())
    logging.info(f"Found {files_count} files in components directory")

    if files_count == 0:
        logging.warning(f"Components directory appears to be empty: {components_path}")

    # Ensure the output directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)

    files_added: int = 0

    with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        # -- 1) Add all files from components directory except excluded
        for root, dirs, files in os.walk(components_path):
            # Filter out excluded dirs so os.walk doesn't descend into them
            dirs[:] = [
                d for d in dirs
                if not any(fnmatch.fnmatch(str(Path(root, d)), pat) for pat in exclude_patterns)
            ]

            for file in files:
                file_path = Path(root) / file
                if any(fnmatch.fnmatch(str(file_path), pat) for pat in exclude_patterns):
                    logging.debug(f"Excluding file: {file_path}")
                    continue

                # Write it to the ZIP with a path relative to components_path
                rel_path = file_path.relative_to(components_path)
                # Put it under src/dc_custom_component/components in the zip
                zip_path = Path("src") / "dc_custom_component" / "components" / rel_path
                zipf.write(file_path, arcname=str(zip_path))
                files_added += 1

        # -- 2) Add __about__.py and __init__.py from dc_custom_component directory
        about_file = about_init_path / "__about__.py"
        init_file = about_init_path / "__init__.py"

        if about_file.exists():
            if not any(fnmatch.fnmatch(str(about_file), pat) for pat in exclude_patterns):
                zipf.write(about_file, arcname="src/dc_custom_component/__about__.py")
                files_added += 1
                logging.info("Added __about__.py to src/dc_custom_component/")
            else:
                logging.debug("Excluding __about__.py due to pattern")
        else:
            logging.warning(f"__about__.py not found in {about_init_path}")

        if init_file.exists():
            if not any(fnmatch.fnmatch(str(init_file), pat) for pat in exclude_patterns):
                zipf.write(init_file, arcname="src/dc_custom_component/__init__.py")
                files_added += 1
                logging.info("Added __init__.py to src/dc_custom_component/")
            else:
                logging.debug("Excluding __init__.py due to pattern")
        else:
            logging.warning(f"__init__.py not found in {about_init_path}")

        # -- 3) Include pyproject.toml from the project root
        pyproject_file = root_path / "pyproject.toml"
        if pyproject_file.exists():
            # Optionally honor exclude patterns here if you want
            if not any(fnmatch.fnmatch(str(pyproject_file), pat) for pat in exclude_patterns):
                zipf.write(pyproject_file, arcname="pyproject.toml")
                files_added += 1
            else:
                logging.debug("Excluding pyproject.toml due to pattern")

        readme_file = root_path / "README.md"
        if readme_file.exists():
            zipf.write(readme_file, arcname="README.md")
            files_added += 1

    logging.info(f"Added {files_added} files to the zip archive")

    # Verify the zip file was created and is non-empty
    if not output_path.exists():
        logging.error(f"Failed to create zip file: {output_path}")
        return False

    if files_added == 0:
        logging.warning(f"Created zip file is empty: {output_path}")

    # List the contents of the zip file for verification
    logging.info("Zip file contents:")
    with zipfile.ZipFile(output_path, 'r') as zipf:
        for info in zipf.infolist():
            logging.info(f"  {info.filename} ({info.file_size} bytes)")

    return True


def main() -> int:
    # Define paths relative to the project root
    project_root = Path.cwd()
    # Updated paths for new directory structure
    components_dir = project_root / "src" / "dc_custom_component" / "components"
    about_init_dir = project_root / "src" / "dc_custom_component"
    dist_dir = project_root / "dist/components"
    output_zip = dist_dir / "custom_component.zip"  # Renamed to dc_custom_component.zip

    logging.info(f"Project root: {project_root}")
    logging.info(f"Components directory: {components_dir}")
    logging.info(f"DC custom component directory: {about_init_dir}")
    logging.info(f"Output zip: {output_zip}")

    # Default exclude patterns
    exclude_patterns: List[str] = [
        '*.env',
        '*venv*',
        '*.pyc',
        '__pycache__/*',
        '*.pyo',
        '.git/*',
        '.gitignore',
        '.DS_Store'
    ]

    # Remove existing dist directory if it exists
    if dist_dir.exists():
        logging.info(f"Removing existing dist/components directory: {dist_dir}")
        shutil.rmtree(dist_dir)

    # Create dist directory
    logging.info(f"Creating dist directory: {dist_dir}")
    dist_dir.mkdir(parents=True, exist_ok=True)

    # Create zip file
    logging.info(f"Creating zip file: {output_zip}")
    success = create_zip_file(
        components_dir=components_dir,
        about_init_dir=about_init_dir,
        output_zip=output_zip,
        project_root=project_root,
        exclude_patterns=exclude_patterns
    )

    if success:
        logging.info(f"Successfully created {output_zip}")
    else:
        logging.error(f"Failed to create {output_zip}")
        return 1

    return 0


if __name__ == "__main__":
    main()