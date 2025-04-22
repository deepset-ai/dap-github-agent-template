import re
from typing import Any, Dict, Optional

import requests
from haystack import component, default_from_dict, default_to_dict, logging
from haystack.utils import deserialize_secrets_inplace
from haystack.utils.auth import Secret

logger = logging.getLogger(__name__)


@component
class GithubBranchCreator:
    """
    Creates a branch for a GitHub issue.

    The component takes a GitHub issue URL and creates a new branch named with pattern 'fix-issue-{number}'.
    It can be configured to either fail or skip if the branch already exists.

    ### Usage example
    ```python
    from haystack.components.github import GithubBranchCreator

    creator = GithubBranchCreator(
        github_token=Secret.from_env_var("GITHUB_TOKEN"),
        fail_if_exists=False
    )
    result = creator.run(
        url="https://github.com/owner/repo/issues/123"
    )

    # Access the branch name
    branch_name = result["branch_name"]
    # Check if branch was newly created
    was_created = result["created"]
    ```

    Any errors during execution will raise exceptions.
    """

    def __init__(
        self,
        github_token: Secret = Secret.from_env_var("GITHUB_TOKEN", strict=False),
        fail_if_exists: bool = True,
        branch_prefix: str = "fix-issue-",
        retry_attempts: int = 2,
    ):
        """
        Initialize the component.

        :param github_token: GitHub personal access token with repo scope for API authentication
        :param fail_if_exists: If True, raises exception when branch already exists; if False, skips creation
        :param branch_prefix: Prefix to use for branch names (default: "fix-issue-")
        :param retry_attempts: Number of retry attempts for failed requests
        """
        self.github_token = github_token
        self.fail_if_exists = fail_if_exists
        self.branch_prefix = branch_prefix
        self.retry_attempts = retry_attempts

        # Basic headers for API requests
        self.headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "Haystack/GithubBranchCreator",
        }

    def _get_request_headers(self) -> dict:
        """
        Get headers with resolved token for the request.

        :return: Dictionary of headers including authorization
        """
        headers = self.headers.copy()
        headers["Authorization"] = f"Bearer {self.github_token.resolve_value()}"
        return headers

    def _parse_github_url(self, url: str) -> tuple[str, str, int]:
        """
        Parse GitHub URL into owner, repo and issue number.

        :param url: GitHub issue URL
        :return: Tuple of (owner, repo, issue_number)
        :raises ValueError: If URL format is invalid
        """
        pattern = r"https?://github\.com/([^/]+)/([^/]+)/issues/(\d+)"
        match = re.match(pattern, url)
        if not match:
            raise ValueError(f"Invalid GitHub issue URL format: {url}")

        owner, repo, issue_number = match.groups()
        return owner, repo, int(issue_number)

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
                return response.json()["default_branch"]  # type: ignore
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
            return response.json()["object"]["sha"]  # type: ignore
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
        return default_to_dict(  # type: ignore
            self,
            github_token=self.github_token.to_dict(),
            fail_if_exists=self.fail_if_exists,
            branch_prefix=self.branch_prefix,
            retry_attempts=self.retry_attempts,
        )

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GithubBranchCreator":
        """
        Deserialize the component from a dictionary.

        :param data: Dictionary to deserialize from.
        :returns: Deserialized component.
        """
        init_params = data["init_parameters"]
        deserialize_secrets_inplace(init_params, keys=["github_token"])
        return default_from_dict(cls, data)  # type: ignore

    @component.output_types(branch_name=str, created=bool)
    def run(self, url: str) -> dict:
        """
        Process a GitHub issue URL and create a branch for it.

        :param url: GitHub issue URL
        :return: Dictionary containing branch name and creation status
        """
        # Parse the GitHub URL
        owner, repo, issue_number = self._parse_github_url(url)

        # Generate branch name
        branch_name = f"{self.branch_prefix}{issue_number}"

        # Get the default branch to use as base
        default_branch = self._get_default_branch(owner, repo)

        # Get the SHA of the latest commit on default branch
        base_sha = self._get_branch_ref(owner, repo, default_branch)
        if not base_sha:
            raise ValueError(
                f"Could not find default branch '{default_branch}' in {owner}/{repo}"
            )

        # Create the branch
        created = self._create_branch(owner, repo, branch_name, base_sha)

        return {"branch_name": branch_name, "created": created}
