from typing import Any, Dict, Optional

from haystack import (
    SuperComponent,
    component,
    Pipeline,
    default_from_dict,
    default_to_dict,
)
from haystack.utils import Secret, deserialize_secrets_inplace
from haystack.components.builders import PromptBuilder

from dc_custom_component.components.github.repo_viewer import GithubRepositoryViewer


@component
class GithubContentViewer(SuperComponent):
    """
    A SuperComponent that combines GithubRepositoryViewer and PromptBuilder to fetch
    and format GitHub repository content.

    For directories:
    - Formats the content as a listing with item paths

    For files:
    - Formats the content with file path and the full file content

    ### Usage example
    ```python
    from haystack.utils import Secret

    viewer = GithubContentViewer(
        repo="owner/repository",
        github_token=Secret.from_token("your_token"),
        branch="main"
    )

    # List directory contents
    result = viewer.run(
        path="docs/"
    )

    # Get specific file
    result = viewer.run(
        path="README.md"
    )
    ```
    """

    def __init__(
        self,
        repo: str,
        github_token: Secret = Secret.from_env_var("GITHUB_TOKEN", strict=False),
        raise_on_failure: bool = True,
        max_file_size: int = 1_000_000,  # 1MB default limit
        branch: Optional[str] = None,
    ):
        """
        Initialize the GitHubContentViewer.

        :param repo: Repository in format "owner/repo"
        :param github_token: GitHub personal access token for API authentication
        :param raise_on_failure: If True, raises exceptions on API errors
        :param max_file_size: Maximum file size in bytes to fetch (default: 1MB)
        :param branch: Default branch to use
        """
        self.repo = repo
        self.github_token = github_token
        self.raise_on_failure = raise_on_failure
        self.max_file_size = max_file_size
        self.branch = branch

        # Create the repository viewer component
        repo_viewer = GithubRepositoryViewer(
            github_token=github_token,
            raise_on_failure=raise_on_failure,
            max_file_size=max_file_size,
            repo=repo,
            branch=branch,
        )

        # Create template for directory listings
        dir_template = """
Directory listing for {{path}}:
{% for doc in documents %}{% if doc.meta.type == 'dir' %}📁 {% else %}📄 {% endif %}{{ doc.meta.path }}
{% endfor %}
"""

        # Create template for file content
        file_template = """
File content for {{path}}:
```
{{ documents[0].content }}
```
"""

        # Create the prompt builder with conditional template
        prompt_builder = PromptBuilder(
            template="""
{% if documents[0].meta.type == 'file_content' %}
"""
            + file_template
            + """
{% else %}
"""
            + dir_template
            + """
{% endif %}
"""
        )

        # Create the internal pipeline
        pp = Pipeline()
        pp.add_component("repo_viewer", repo_viewer)
        pp.add_component("prompt_builder", prompt_builder)

        # Connect components
        pp.connect("repo_viewer.documents", "prompt_builder.documents")

        # Initialize the parent SuperComponent with the pipeline
        super(GithubContentViewer, self).__init__(
            pipeline=pp,
            input_mapping={
                "path": ["repo_viewer.path", "prompt_builder.path"],
                "branch": ["repo_viewer.branch"],
            },
            output_mapping={
                "prompt_builder.prompt": "result",
            },
        )

    def to_dict(self) -> Dict[str, Any]:
        """
        Serialize the component to a dictionary.

        :returns: Dictionary with serialized data.
        """
        return default_to_dict(  # type: ignore
            self,
            repo=self.repo,
            github_token=self.github_token.to_dict() if self.github_token else None,
            raise_on_failure=self.raise_on_failure,
            max_file_size=self.max_file_size,
            branch=self.branch,
        )

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GithubContentViewer":
        """
        Deserialize the component from a dictionary.

        :param data: Dictionary to deserialize from.
        :returns: Deserialized component.
        """
        init_params = data["init_parameters"]
        deserialize_secrets_inplace(init_params, keys=["github_token"])
        return default_from_dict(cls, data)  # type: ignore
