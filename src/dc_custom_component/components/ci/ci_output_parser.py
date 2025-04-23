from typing import Any, Dict

from haystack import component, default_from_dict, default_to_dict, logging

logger = logging.getLogger(__name__)


@component
class CIOutputParser:
    """
    Processes CI output for the CI agent pipeline.

    This component simply passes the raw CI output and repository information
    to be used directly by the agent. No document parsing is performed.

    ### Usage example
    ```python
    from dc_custom_component.components.ci import CIOutputParser

    parser = CIOutputParser()
    result = parser.run(
        ci_output="Test failed: test_example.py::test_function\nSyntaxError in file.py line 10",
        repo="owner/repo",
        issue_url="https://github.com/owner/repo/issues/123"
    )
    ```
    """

    def __init__(
        self,
        raise_on_failure: bool = True,
    ):
        """
        Initialize the component.

        :param raise_on_failure: If True, raises exceptions on processing errors
        """
        self.raise_on_failure = raise_on_failure

    def to_dict(self) -> Dict[str, Any]:
        """
        Serialize the component to a dictionary.

        :returns: Dictionary with serialized data.
        """
        return default_to_dict(
            self,
            raise_on_failure=self.raise_on_failure,
        )

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CIOutputParser":
        """
        Deserialize the component from a dictionary.

        :param data: Dictionary to deserialize from.
        :returns: Deserialized component.
        """
        return default_from_dict(cls, data)

    @component.output_types(ci_output=str, repo=str, issue_url=str)
    def run(self, ci_output: str, repo: str, issue_url: str) -> dict:
        """
        Process CI output and pass it along with repo information.

        :param ci_output: CI run output text
        :param repo: Repository name in format "owner/repo"
        :param issue_url: URL of the issue that triggered the original workflow
        :return: Dictionary containing the CI output and repo info
        """
        try:
            return {"ci_output": ci_output, "repo": repo, "issue_url": issue_url}
        except Exception as e:
            if self.raise_on_failure:
                raise

            error_message = f"Error processing CI output: {str(e)}"
            logger.warning(error_message)
            return {"ci_output": error_message, "repo": repo, "issue_url": issue_url}
