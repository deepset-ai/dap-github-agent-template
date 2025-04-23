import re
from typing import Any, Dict, Optional

import requests
from haystack import component, default_from_dict, default_to_dict, logging
from haystack.utils import deserialize_secrets_inplace
from haystack.utils.auth import Secret

logger = logging.getLogger(__name__)


@component
class CIBranchCreator:
    """
    Creates a branch for a CI run fix.

    The component takes a repository name and creates a new branch named with pattern 'fix-ci-{timestamp}'.
    It can be configured to either fail or skip if the branch already exists.

    ### Usage example
    ```python
    from dc_custom_component.components.ci import CIBranchCreator

    creator = CIBranchCreator(
        github_token=Secret.from_env_var("GITHUB_TOKEN"),
        fail_if_exists=False
    )
    result = creator.run(
        repo="owner/repo"
    )

    # Access the branch name
    branch_name = result["branch_name"]
    # Check if branch was newly created
    was_created = result["created"]
    ```
    """

    def __init__(
        self,
        github_token: Secret = Secret.from_env_var("GITHUB_TOKEN", strict=False),
        fail_if_exists: bool = True,
        branch_prefix: str = "fix-ci-",
        retry_attempts: int = 2,
    ):
        """
        Initialize the component.

        :param github_token: GitHub personal access token with repo scope for API authentication
        :param fail_if_exists: If True, raises exception when branch already exists; if False, skips creation
        :param branch_prefix: Prefix to use for branch names (default: "fix-ci-")
        :param retry_attempts: Number of retry attempts for failed requests
        """
        self.github_token = github_token
        self.fail_if_exists = fail_if_exists
        self.branch_prefix = branch_prefix
        self.retry_attempts = retry_attempts

        # Basic headers for API requests
        self.headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "Haystack/CIBranchCreator",
        }

    def _get_request_headers(self) -> dict:
        """
        Get headers with resolved token for the request.

        :return: Dictionary of headers including authorization
        """
        headers = self.headers.copy()
        headers["Authorization"] = f"Bearer {self.github_token.resolve_value()}"
        return headers

    def _parse_repo(self, repo: str) -> tuple[str, str]:
        """
        Parse repository string into owner and repo name.

        :param repo: Repository in format "owner/repo"
        :return: Tuple of (owner, repo)
        :raises ValueError: If repo format is invalid
        """
        parts = repo.split('/')
        if len(parts) != 2:
            raise ValueError(f"Invalid repository format: {repo}. Expected format: 'owner/repo'")
        
        owner, repo_name = parts
        return owner, repo_name

    def _get_default_branch(self, owner: str, repo: str) -> str:
        """
        Get the default branch of the repository.

        :param owner: Repository owner
        :param repo: Repository name
        :return: The name of the default branch
        """
        url = f"https://api.github.com/repos/{owner}/{repo}"

        for attempt in range(self.retry_attempts + 1):
            try:
                response = requests.get(url, headers=self._get_request_headers())
                response.raise_for_status()
                return response.json()["default_branch"]
            except Exception as e:
                if attempt == self.retry_attempts:
                    raise
                logger.warning(f"Failed to get default branch, retrying: {str(e)}")

        # This should never be reached, but added for type safety
        raise RuntimeError("Failed to get default branch after retries")

    def _get_branch_ref(self, owner: str, repo: str, branch: str) -> Optional[str]:
        """
        Check if a branch exists in the repository.

        :param owner: Repository owner
        :param repo: Repository name
        :param branch: Branch name to check
        :return: SHA of the branch head if it exists, None otherwise
        """
        url = f"https://api.github.com/repos/{owner}/{repo}/git/refs/heads/{branch}"

        try:
            response = requests.get(url, headers=self._get_request_headers())
            if response.status_code == 404:
                return None
            response.raise_for_status()
            return response.json()["object"]["sha"]
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                return None
            raise

    def _create_branch(
        self, owner: str, repo: str, branch_name: str, base_sha: str
    ) -> bool:
        """
        Create a new branch in the repository.

        :param owner: Repository owner
        :param repo: Repository name
        :param branch_name: Name for the new branch
        :param base_sha: SHA of the commit to base the branch on
        :return: True if branch was created, False if it already existed
        """
        # Check if branch already exists
        if self._get_branch_ref(owner, repo, branch_name):
            if self.fail_if_exists:
                raise ValueError(
                    f"Branch '{branch_name}' already exists in {owner}/{repo}"
                )
            return False

        # Create the branch
        url = f"https://api.github.com/repos/{owner}/{repo}/git/refs"
        payload = {"ref": f"refs/heads/{branch_name}", "sha": base_sha}

        for attempt in range(self.retry_attempts + 1):
            try:
                response = requests.post(
                    url, json=payload, headers=self._get_request_headers()
                )
                response.raise_for_status()
                return True
            except Exception as e:
                if attempt == self.retry_attempts:
                    raise
                logger.warning(f"Failed to create branch, retrying: {str(e)}")

        # This should never be reached, but added for type safety
        raise RuntimeError("Failed to create branch after retries")

    def to_dict(self) -> Dict[str, Any]:
        """
        Serialize the component to a dictionary.

        :returns: Dictionary with serialized data.
        """
        return default_to_dict(
            self,
            github_token=self.github_token.to_dict(),
            fail_if_exists=self.fail_if_exists,
            branch_prefix=self.branch_prefix,
            retry_attempts=self.retry_attempts,
        )

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CIBranchCreator":
        """
        Deserialize the component from a dictionary.

        :param data: Dictionary to deserialize from.
        :returns: Deserialized component.
        """
        init_params = data["init_parameters"]
        deserialize_secrets_inplace(init_params, keys=["github_token"])
        return default_from_dict(cls, data)

    @component.output_types(branch_name=str, created=bool)
    def run(self, repo: str) -> dict:
        """
        Process a repo string and create a branch for CI fixes.

        :param repo: Repository in format "owner/repo"
        :return: Dictionary containing branch name and creation status
        """
        # Parse the repo string
        owner, repo_name = self._parse_repo(repo)

        # Generate branch name with timestamp to ensure uniqueness
        import time
        timestamp = int(time.time())
        branch_name = f"{self.branch_prefix}{timestamp}"

        # Get the default branch to use as base
        default_branch = self._get_default_branch(owner, repo_name)

        # Get the SHA of the latest commit on default branch
        base_sha = self._get_branch_ref(owner, repo_name, default_branch)
        if not base_sha:
            raise ValueError(
                f"Could not find default branch '{default_branch}' in {owner}/{repo_name}"
            )

        # Create the branch
        created = self._create_branch(owner, repo_name, branch_name, base_sha)

        return {"branch_name": branch_name, "created": created}
