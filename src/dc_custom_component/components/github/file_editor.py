from enum import StrEnum
from typing import Any, Dict, Optional, Union
import requests
from haystack import component, logging, default_from_dict, default_to_dict
from haystack.utils import Secret, deserialize_secrets_inplace
from base64 import b64encode, b64decode

logger = logging.getLogger(__name__)


class Command(StrEnum):
    """Available commands for file operations in GitHub.

    Attributes:
        EDIT: Edit an existing file by replacing content
        UNDO: Revert the last commit if made by the same user
        CREATE: Create a new file
        DELETE: Delete an existing file
    """

    EDIT = "edit"
    UNDO = "undo"
    CREATE = "create"
    DELETE = "delete"


@component
class GithubFileEditor:
    """
    A Haystack component for editing files in GitHub repositories.

    Supports editing, undoing changes, deleting files, and creating new files
    through the GitHub API.

    ### Usage example
    ```python
    from haystack.components.actions import GithubFileEditor
    from haystack.utils import Secret

    # Initialize with default repo and branch
    editor = GithubFileEditor(
        github_token=Secret.from_env_var("GITHUB_TOKEN"),
        repo="owner/repo",
        branch="main"
    )

    # Edit a file using default repo and branch
    result = editor.run(
        command=Command.EDIT,
        payload={
            "path": "path/to/file.py",
            "original": "def old_function():",
            "replacement": "def new_function():",
            "message": "Renamed function for clarity"
        }
    )

    # Edit a file in a different repo/branch
    result = editor.run(
        command=Command.EDIT,
        repo="other-owner/other-repo",  # Override default repo
        branch="feature",  # Override default branch
        payload={
            "path": "path/to/file.py",
            "original": "def old_function():",
            "replacement": "def new_function():",
            "message": "Renamed function for clarity"
        }
    )
    ```
    """

    def __init__(
        self,
        github_token: Secret = Secret.from_env_var("GITHUB_TOKEN", strict=False),
        repo: Optional[str] = None,
        branch: str = "main",
        raise_on_failure: bool = True,
    ):
        """
        Initialize the component.

        :param github_token: GitHub personal access token for API authentication
        :param repo: Default repository in owner/repo format
        :param branch: Default branch to work with
        :param raise_on_failure: If True, raises exceptions on API errors
        """
        if not isinstance(github_token, Secret):
            raise TypeError("github_token must be a Secret")

        self.github_token = github_token
        self.default_repo = repo
        self.default_branch = branch
        self.raise_on_failure = raise_on_failure

        self.headers = {
            "Accept": "application/vnd.github.v3+json",
            "Authorization": f"Bearer {self.github_token.resolve_value()}",
            "User-Agent": "Haystack/GithubFileEditor",
        }

    def _get_file_content(
        self, owner: str, repo: str, path: str, branch: str
    ) -> tuple[str, str]:
        """Get file content and SHA from GitHub."""
        url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}"
        params: dict[str, str] = {"ref": branch}
        response = requests.get(url, headers=self.headers, params=params)
        response.raise_for_status()
        data = response.json()
        content = b64decode(data["content"]).decode("utf-8")
        sha: str = data["sha"]
        return content, sha

    def _update_file(
        self,
        owner: str,
        repo: str,
        path: str,
        content: str,
        message: str,
        sha: str,
        branch: str,
    ) -> bool:
        """Update file content on GitHub."""
        url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}"
        payload = {
            "message": message,
            "content": b64encode(content.encode("utf-8")).decode("utf-8"),
            "sha": sha,
            "branch": branch,
        }
        response = requests.put(url, headers=self.headers, json=payload)
        response.raise_for_status()
        return True

    def _check_last_commit(self, owner: str, repo: str, branch: str) -> bool:
        """Check if last commit was made by the current token user."""
        url = f"https://api.github.com/repos/{owner}/{repo}/commits"
        params_dict: dict[str, int | str] = {"per_page": 1, "sha": branch}
        response = requests.get(url, headers=self.headers, params=params_dict)
        response.raise_for_status()
        last_commit = response.json()[0]
        commit_author = last_commit["author"]["login"]

        # Get current user
        user_response = requests.get(
            "https://api.github.com/user", headers=self.headers
        )
        user_response.raise_for_status()
        current_user = user_response.json()["login"]

        return bool(commit_author == current_user)

    def _edit_file(
        self, owner: str, repo: str, payload: Dict[str, str], branch: str
    ) -> str:
        """Handle file editing."""
        try:
            content, sha = self._get_file_content(owner, repo, payload["path"], branch)

            # Check if original string is unique
            occurrences = content.count(payload["original"])
            if occurrences == 0:
                return "Error: Original string not found in file"
            if occurrences > 1:
                return "Error: Original string appears multiple times. Please provide more context"

            # Perform the replacement
            new_content = content.replace(payload["original"], payload["replacement"])
            success = self._update_file(
                owner,
                repo,
                payload["path"],
                new_content,
                payload["message"],
                sha,
                branch,
            )
            return "Edit successful" if success else "Edit failed"

        except requests.RequestException as e:
            if self.raise_on_failure:
                raise
            return f"Error: {str(e)}"

    def _undo_changes(
        self, owner: str, repo: str, payload: Dict[str, str], branch: str
    ) -> str:
        """Handle undoing changes."""
        try:
            if not self._check_last_commit(owner, repo, branch):
                return "Error: Last commit was not made by the current user"

            # Reset to previous commit
            url = f"https://api.github.com/repos/{owner}/{repo}/git/refs/heads/{branch}"
            commits_url = f"https://api.github.com/repos/{owner}/{repo}/commits"

            # Get the previous commit SHA
            params_dict: dict[str, int | str] = {"per_page": 2, "sha": branch}
            commits = requests.get(
                commits_url, headers=self.headers, params=params_dict
            ).json()
            previous_sha: str = commits[1]["sha"]

            # Update branch reference to previous commit
            update_payload: dict[str, str | bool] = {"sha": previous_sha, "force": True}
            response = requests.patch(url, headers=self.headers, json=update_payload)
            response.raise_for_status()

            return "Successfully undid last change"

        except requests.RequestException as e:
            if self.raise_on_failure:
                raise
            return f"Error: {str(e)}"

    def _create_file(
        self, owner: str, repo: str, payload: Dict[str, str], branch: str
    ) -> str:
        """Handle file creation."""
        try:
            url = f"https://api.github.com/repos/{owner}/{repo}/contents/{payload['path']}"
            content = b64encode(payload["content"].encode("utf-8")).decode("utf-8")

            data = {"message": payload["message"], "content": content, "branch": branch}

            response = requests.put(url, headers=self.headers, json=data)
            response.raise_for_status()
            return "File created successfully"

        except requests.RequestException as e:
            if self.raise_on_failure:
                raise
            return f"Error: {str(e)}"

    def _delete_file(
        self, owner: str, repo: str, payload: Dict[str, str], branch: str
    ) -> str:
        """Handle file deletion."""
        try:
            content, sha = self._get_file_content(owner, repo, payload["path"], branch)
            url = f"https://api.github.com/repos/{owner}/{repo}/contents/{payload['path']}"

            data = {"message": payload["message"], "sha": sha, "branch": branch}

            response = requests.delete(url, headers=self.headers, json=data)
            response.raise_for_status()
            return "File deleted successfully"

        except requests.RequestException as e:
            if self.raise_on_failure:
                raise
            return f"Error: {str(e)}"

    @component.output_types(result=str)
    def run(
        self,
        command: Union[Command, str],
        payload: Dict[str, Any],
        repo: Optional[str] = None,
        branch: Optional[str] = None,
    ) -> Dict[str, str]:
        """
        Process GitHub file operations.

        :param command: Operation to perform ("edit", "undo", "create", "delete")
        :param payload: Dictionary containing command-specific parameters
        :param repo: Repository in owner/repo format (overrides default if provided)
        :param branch: Branch to perform operations on (overrides default if provided)
        :return: Dictionary containing operation result
        """
        if repo is None:
            if self.default_repo is None:
                return {
                    "result": "Error: No repository specified. Either provide it in initialization or in run() method"
                }
            repo = self.default_repo  # At this point repo is guaranteed to be a string

        working_branch = branch if branch is not None else self.default_branch
        owner, repo_name = repo.split("/")

        command_handlers: Dict[Command, Any] = {
            Command.EDIT: self._edit_file,
            Command.UNDO: self._undo_changes,
            Command.CREATE: self._create_file,
            Command.DELETE: self._delete_file,
        }

        if command not in command_handlers:
            return {"result": f"Error: Unknown command '{command}'"}

        # Convert string command to Command enum if needed
        cmd = Command(command) if isinstance(command, str) else command
        handler = command_handlers[cmd]
        result = handler(owner, repo_name, payload, working_branch)
        return {"result": result}

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the component to a dictionary."""
        return default_to_dict(  # type: ignore
            self,
            github_token=self.github_token.to_dict() if self.github_token else None,
            repo=self.default_repo,
            branch=self.default_branch,
            raise_on_failure=self.raise_on_failure,
        )

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GithubFileEditor":
        """Deserialize the component from a dictionary."""
        init_params = data["init_parameters"]
        deserialize_secrets_inplace(init_params, keys=["github_token"])  # type: ignore
        return default_from_dict(cls, data)  # type: ignore
