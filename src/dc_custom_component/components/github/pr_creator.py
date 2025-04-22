from typing import Any, Dict, Optional

import requests
from haystack import component, default_from_dict, default_to_dict, logging
from haystack.utils import deserialize_secrets_inplace
from haystack.utils.auth import Secret

logger = logging.getLogger(__name__)


@component
class GitHubPRCreator:
    """
    Creates a GitHub Pull Request for a specified branch.

    This component allows you to create a Pull Request on GitHub by providing:
    - Repository owner and name
    - Head branch (the branch with your changes)
    - Base branch (the branch you want to merge into, typically 'main' or 'master')
    - PR title and body (description)

    ### Usage example
    ```python
    from haystack.utils.auth import Secret
    from dc_custom_component.components.github.pr_creator import GitHubPRCreator

    pr_creator = GitHubPRCreator(
        github_token=Secret.from_env_var("GITHUB_TOKEN"),
        repo="repo-name/repo-owner"
    )

    result = pr_creator.run(
        head_branch="feature-branch",
        base_branch="main",
        title="Add new feature",
        body="This PR adds a new feature that does X, Y, and Z."
    )

    print(f"Pull Request created: {result['pr_url']}")
    ```
    """

    def __init__(
        self,
        repo: Optional[str] = None,
        github_token: Secret = Secret.from_env_var("GITHUB_TOKEN", strict=False),
        base_branch: str = "main",
        draft: bool = False,
        maintainer_can_modify: bool = True,
        retry_attempts: int = 2,
    ):
        """
        Initialize the component.

        :param github_token: GitHub personal access token for API authentication
        :param repo: owner/repo
        :param base_branch: Default branch to merge PRs into (typically 'main' or 'master')
        :param draft: If True, creates the PR as a draft
        :param maintainer_can_modify: If True, allows maintainers to modify the PR
        :param retry_attempts: Number of retry attempts for failed requests
        """
        if not github_token:
            raise ValueError("GitHub token is required for creating pull requests")

        self.github_token = github_token
        self.repo = repo
        self.base_branch = base_branch
        self.draft = draft
        self.maintainer_can_modify = maintainer_can_modify
        self.retry_attempts = retry_attempts

        # Set up the headers for GitHub API requests
        self.base_headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "Haystack/GitHubPRCreator",
        }

    def _get_request_headers(self) -> dict:
        """
        Get headers with resolved token for the request.

        :return: Dictionary of headers including authorization
        """
        headers = self.base_headers.copy()
        headers["Authorization"] = f"Bearer {self.github_token.resolve_value()}"
        return headers

    def _create_pull_request(
        self, head_branch: str, base_branch: str, title: str, body: str, repo: str
    ) -> Dict[str, Any]:
        """
        Create a pull request via the GitHub API.

        :param head_branch: Branch containing the changes
        :param base_branch: Branch to merge changes into
        :param title: Pull request title
        :param body: Pull request description
        :param repo: owner/repo
        :return: API response data
        """
        owner, repository = repo.split("/")

        url = f"https://api.github.com/repos/{owner}/{repository}/pulls"

        data = {
            "head": head_branch,
            "base": base_branch,
            "title": title,
            "body": body,
            "draft": self.draft,
            "maintainer_can_modify": self.maintainer_can_modify,
        }

        response = requests.post(url, headers=self._get_request_headers(), json=data)
        response.raise_for_status()
        return response.json()  # type: ignore

    def to_dict(self) -> Dict[str, Any]:
        """
        Serialize the component to a dictionary.

        :returns: Dictionary with serialized data.
        """
        return default_to_dict(  # type: ignore
            self,
            github_token=self.github_token.to_dict(),
            repo=self.repo,
            base_branch=self.base_branch,
            draft=self.draft,
            maintainer_can_modify=self.maintainer_can_modify,
            retry_attempts=self.retry_attempts,
        )

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GitHubPRCreator":
        """
        Deserialize the component from a dictionary.

        :param data: Dictionary to deserialize from.
        :returns: Deserialized component.
        """
        init_params = data["init_parameters"]
        deserialize_secrets_inplace(init_params, keys=["github_token"])
        return default_from_dict(cls, data)  # type: ignore

    @component.output_types(pr_url=str, pr_number=int, pr_data=Dict[str, Any])
    def run(
        self,
        head_branch: str,
        title: str,
        body: str = "",
        repo: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Create a pull request on GitHub.

        :param head_branch: Branch containing the changes
        :param title: Pull request title
        :param body: Pull request description/body
        :param repo: owner/repo for which to create the pull request
        :return: Dictionary containing PR URL, number, and full response data
        """


        # Determine which repo to use
        repo_to_use = repo if repo is not None else self.repo

        # Ensure repo_to_use is a string, not None
        if repo_to_use is None:
            raise ValueError("You need to specify a repo to create the pull request. Pass `repo` either to the constructor or to the `run`-method.")
            
        # At this point, repo_to_use is guaranteed to be a string
        repo_to_use = str(repo_to_use)

        if len(repo_to_use.split("/")) != 2:
            raise ValueError("Invalid format for `repo`. The format has to correspond to owner/repo.")

        attempts = 0
        last_error = None

        target_base = self.base_branch

        while attempts <= self.retry_attempts:
            try:
                pr_data = self._create_pull_request(
                    head_branch=head_branch,
                    base_branch=target_base,
                    title=title,
                    body=body,
                    repo=repo_to_use,
                )

                return {
                    "pr_url": pr_data["html_url"],
                    "pr_number": pr_data["number"],
                    "pr_data": pr_data,
                }

            except Exception as e:
                attempts += 1
                last_error = e
                if attempts <= self.retry_attempts:
                    logger.warning(f"Attempt {attempts} failed: {str(e)}. Retrying...")
                else:
                    break

        # If we get here, all attempts failed
        error_message = f"Failed to create PR after {self.retry_attempts + 1} attempts. Last error: {str(last_error)}"
        logger.error(error_message)
        raise RuntimeError(error_message)
